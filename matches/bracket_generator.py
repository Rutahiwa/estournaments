"""
Bracket generator: randomized single-elimination (cup) and round-robin (league).
"""
import random
from .models import Match, LeagueStanding
from tournaments.models import Participant, Tournament

def get_round_name(round_number, total_rounds):
    """
    Return human-readable round name for cup tournaments.
    Example: Round 1, Quarter-finals, Semi-finals, Final
    """
    if round_number == total_rounds:
        return "Final"
    elif round_number == total_rounds - 1:
        return "Semi-finals"
    elif round_number == total_rounds - 2:
        return "Quarter-finals"
    else:
        return f"Round {round_number}"

def generate_single_elimination_bracket(tournament):
    """
    Create round 1 matches for cup tournament with randomized pairings.
    Requires an even number of participants.
    """
    if tournament.tournament_type != Tournament.TOURNAMENT_TYPE_CUP:
        raise ValueError(f"Tournament is type '{tournament.tournament_type}', not 'cup'.")
    
    participants = list(Participant.objects.filter(tournament=tournament))
    if len(participants) < 2:
        raise ValueError("Tournament must have at least 2 participants.")
    random.shuffle(participants)
    if len(participants) % 2 != 0:
        raise ValueError("Tournament participant count must be even for single-elimination (2,4,8...).")
    
    matches = []
    for i in range(0, len(participants), 2):
        m = Match.objects.create(
            tournament=tournament,
            participant_a=participants[i],
            participant_b=participants[i+1],
            round_number=1,
            status=Match.STATUS_PENDING
        )
        matches.append(m)
    return matches


def generate_league_matches(tournament):
    """
    Create all round-robin matches for league tournament.
    Every participant plays every other participant exactly once.
    """
    if tournament.tournament_type != Tournament.TOURNAMENT_TYPE_LEAGUE:
        raise ValueError(f"Tournament is type '{tournament.tournament_type}', not 'league'.")
    
    participants = list(Participant.objects.filter(tournament=tournament))
    if len(participants) < 2:
        raise ValueError("Tournament must have at least 2 participants.")
    
    # Create LeagueStanding records for all participants
    for participant in participants:
        LeagueStanding.objects.get_or_create(
            tournament=tournament,
            participant=participant,
            defaults={'played': 0, 'won': 0, 'drew': 0, 'lost': 0, 'goals_for': 0, 'goals_against': 0}
        )
    
    # Generate all pairings (round-robin)
    matches = []
    matchday = 1
    for i, p1 in enumerate(participants):
        for p2 in participants[i+1:]:
            m = Match.objects.create(
                tournament=tournament,
                participant_a=p1,
                participant_b=p2,
                round_number=matchday,  # In league, round_number = matchday
                status=Match.STATUS_PENDING
            )
            matches.append(m)
    return matches


def generate_next_round(tournament, current_round):
    """
    Create next round matches from winners of current_round (CUP ONLY).
    If odd winners, create bye match and auto-advance that bye's winner.
    Raises ValueError if some matches in the round are still pending or if league tournament.
    """
    if tournament.tournament_type == Tournament.TOURNAMENT_TYPE_LEAGUE:
        raise ValueError("generate_next_round() not applicable for league tournaments.")
    
    current_matches = Match.objects.filter(tournament=tournament, round_number=current_round)
    pending = current_matches.exclude(status=Match.STATUS_COMPLETED)
    if pending.exists():
        raise ValueError("Not all matches in the current round are completed.")
    
    winners = [m.winner for m in current_matches if m.winner is not None]
    if len(winners) <= 1:
        return []
    
    random.shuffle(winners)
    next_round = current_round + 1
    created = []
    for i in range(0, len(winners), 2):
        if i+1 < len(winners):
            m = Match.objects.create(
                tournament=tournament,
                participant_a=winners[i],
                participant_b=winners[i+1],
                round_number=next_round,
                status=Match.STATUS_PENDING
            )
            created.append(m)
        else:
            bye = Match.objects.create(
                tournament=tournament,
                participant_a=winners[i],
                participant_b=None,
                round_number=next_round,
                status=Match.STATUS_PENDING
            )
            bye.auto_advance_bye_winner()
            created.append(bye)
    return created