"""
Bracket generator helpers: randomized single-elimination and next-round creation.
"""
import random
from .models import Match
from tournaments.models import Participant

def generate_single_elimination_bracket(tournament):
    """
    Create round 1 matches with randomized pairings.
    Requires an even number of participants (bye handling auto-advances one participant if implemented).
    """
    participants = list(Participant.objects.filter(tournament=tournament))
    if len(participants) < 2:
        raise ValueError("Tournament must have at least 2 participants.")
    random.shuffle(participants)
    # require even participants for now (bye will be auto-generated if odd)
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


def generate_next_round(tournament, current_round):
    """
    Create next round matches from winners of current_round.
    If odd winners, create bye match and auto-advance that bye's winner.
    Raises ValueError if some matches in the round are still pending.
    """
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
            # auto-complete bye
            bye.auto_advance_bye_winner()
            created.append(bye)
    return created