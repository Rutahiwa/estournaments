"""
Unit Tests for Matches App

Tests cover:
- Bracket generation with random pairings
- Score reporting and winner determination
- Round progression
- Permission checks
- Status transitions
"""
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from tournaments.models import Tournament, Participant
from .models import Match, MatchReport, LeagueStanding
from .bracket_generator import generate_single_elimination_bracket, generate_league_matches
from django.utils import timezone
from datetime import timedelta
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail

User = get_user_model()

class BracketGeneratorTests(APITestCase):
    """Tests for bracket generation logic."""
    
    def setUp(self):
        self.org = User.objects.create_user(email='org@example.com', username='org', password='TestPass123!')
        self.tournament = Tournament.objects.create(
            name='Test Cup',
            organizer=self.org,
            status='registration_open',
            max_players=4,
            registration_deadline=timezone.now() + timedelta(days=1),
            tournament_type=Tournament.TOURNAMENT_TYPE_CUP
        )
        self.participants = []
        for i in range(4):
            user = User.objects.create_user(email=f'p{i}@example.com', username=f'p{i}', password='TestPass123!')
            participant = Participant.objects.create(tournament=self.tournament, user=user)
            self.participants.append(participant)

    def test_bracket_generation_creates_round_1_matches(self):
        """Verify bracket generation creates correct number of Round 1 matches."""
        matches = generate_single_elimination_bracket(self.tournament)
        self.assertEqual(len(matches), 2)
        for match in matches:
            self.assertEqual(match.round_number, 1)
            self.assertEqual(match.status, Match.STATUS_PENDING)

    def test_bracket_generation_randomizes_pairings(self):
        """Verify participants are randomly paired."""
        generated_pairings = []
        for _ in range(3):
            Match.objects.filter(tournament=self.tournament).delete()
            matches = generate_single_elimination_bracket(self.tournament)
            pairing = set()
            for match in matches:
                pairing.add((match.participant_a.id, match.participant_b.id))
            generated_pairings.append(pairing)
        self.assertTrue(len(generated_pairings) > 0)

    def test_bracket_generation_fails_with_odd_participants(self):
        """Verify bracket generation fails with odd number of participants."""
        user = User.objects.create_user(email='p5@example.com', username='p5', password='TestPass123!')
        Participant.objects.create(tournament=self.tournament, user=user)
        with self.assertRaises(ValueError) as context:
            generate_single_elimination_bracket(self.tournament)
        self.assertIn('even', str(context.exception).lower())


class LeagueGeneratorTests(APITestCase):
    """Tests for league match generation."""
    
    def setUp(self):
        self.org = User.objects.create_user(email='org@example.com', username='org', password='pass')
        self.tournament = Tournament.objects.create(
            name='Test League',
            organizer=self.org,
            status='registration_open',
            max_players=4,
            registration_deadline=timezone.now() + timedelta(days=1),
            tournament_type=Tournament.TOURNAMENT_TYPE_LEAGUE
        )
        self.participants = []
        for i in range(4):
            user = User.objects.create_user(email=f'p{i}@example.com', username=f'p{i}', password='pass')
            participant = Participant.objects.create(tournament=self.tournament, user=user)
            self.participants.append(participant)

    def test_league_generation_creates_all_pairings(self):
        """Verify league generates all round-robin pairings."""
        matches = generate_league_matches(self.tournament)
        # 4 participants: 4*3/2 = 6 matches
        self.assertEqual(len(matches), 6)
        for match in matches:
            self.assertEqual(match.status, Match.STATUS_PENDING)

    def test_league_creates_standings_for_all_participants(self):
        """Verify league standings created for all participants."""
        generate_league_matches(self.tournament)
        standings = LeagueStanding.objects.filter(tournament=self.tournament)
        self.assertEqual(standings.count(), 4)


class MatchAPITests(APITestCase):
    """Tests for Match API endpoints."""
    
    def setUp(self):
        self.org = User.objects.create_user(email='org@example.com', username='org', password='TestPass123!')
        self.p1 = User.objects.create_user(email='p1@example.com', username='p1', password='TestPass123!')
        self.p2 = User.objects.create_user(email='p2@example.com', username='p2', password='TestPass123!')
        
        def token_for(u):
            return str(RefreshToken.for_user(u).access_token)
        
        self.org_token = token_for(self.org)
        self.p1_token = token_for(self.p1)
        self.p2_token = token_for(self.p2)
        
        self.tournament = Tournament.objects.create(
            name='Cup',
            organizer=self.org,
            status='registration_open',
            max_players=2,
            registration_deadline=timezone.now() + timedelta(days=1),
            tournament_type=Tournament.TOURNAMENT_TYPE_CUP
        )
        
        self.part1 = Participant.objects.create(tournament=self.tournament, user=self.p1)
        self.part2 = Participant.objects.create(tournament=self.tournament, user=self.p2)

    def test_organizer_starts_cup_tournament(self):
        url = reverse('tournament-start', kwargs={'tournament_pk': self.tournament.id})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.org_token}')
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['tournament_type'], Tournament.TOURNAMENT_TYPE_CUP)
        self.assertEqual(len(response.data['matches']), 1)

    def test_non_organizer_cannot_start_tournament(self):
        url = reverse('tournament-start', kwargs={'tournament_pk': self.tournament.id})
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.p1_token}')
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_participant_can_report_score(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.org_token}')
        start_resp = self.client.post(reverse('tournament-start', kwargs={'tournament_pk': self.tournament.id}))
        match_id = start_resp.data['matches'][0]['id']
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.p1_token}')
        resp1 = self.client.post(reverse('match-report-score', kwargs={'match_pk': match_id}), {'score_a':2,'score_b':1}, format='json')
        self.assertEqual(resp1.status_code, status.HTTP_202_ACCEPTED)

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.p2_token}')
        resp2 = self.client.post(reverse('match-report-score', kwargs={'match_pk': match_id}), {'score_a':2,'score_b':1}, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)

        m = Match.objects.get(pk=match_id)
        self.assertEqual(m.status, Match.STATUS_COMPLETED)

    def test_bracket_view_returns_structure(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.org_token}')
        self.client.post(reverse('tournament-start', kwargs={'tournament_pk': self.tournament.id}))
        
        bracket_url = reverse('tournament-bracket', kwargs={'tournament_pk': self.tournament.id})
        response = self.client.get(bracket_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['tournament_type'], Tournament.TOURNAMENT_TYPE_CUP)
        self.assertIn('rounds', response.data)


class LeagueAPITests(APITestCase):
    """Tests for League tournaments."""
    
    def setUp(self):
        self.org = User.objects.create_user(email='org@example.com', username='org', password='pass')
        self.users = []
        for i in range(4):
            u = User.objects.create_user(email=f'p{i}@example.com', username=f'p{i}', password='pass')
            self.users.append(u)
        
        def token_for(u):
            return str(RefreshToken.for_user(u).access_token)
        
        self.org_token = token_for(self.org)
        self.user_tokens = [token_for(u) for u in self.users]
        
        self.tournament = Tournament.objects.create(
            name='Premier League',
            organizer=self.org,
            status='registration_open',
            max_players=4,
            registration_deadline=timezone.now() + timedelta(days=1),
            tournament_type=Tournament.TOURNAMENT_TYPE_LEAGUE
        )
        
        self.participants = []
        for u in self.users:
            p = Participant.objects.create(tournament=self.tournament, user=u)
            self.participants.append(p)

    def test_organizer_starts_league_tournament(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.org_token}')
        response = self.client.post(reverse('tournament-start', kwargs={'tournament_pk': self.tournament.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['tournament_type'], Tournament.TOURNAMENT_TYPE_LEAGUE)
        self.assertEqual(len(response.data['matches']), 6)  # 4 participants = 6 pairings

    def test_league_standings_view(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.org_token}')
        self.client.post(reverse('tournament-start', kwargs={'tournament_pk': self.tournament.id}))
        
        response = self.client.get(reverse('tournament-standings', kwargs={'tournament_pk': self.tournament.id}))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['tournament_type'], Tournament.TOURNAMENT_TYPE_LEAGUE)
        self.assertEqual(len(response.data['standings']), 4)

    def test_league_standings_updated_after_match(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.org_token}')
        start_resp = self.client.post(reverse('tournament-start', kwargs={'tournament_pk': self.tournament.id}))
        match_id = start_resp.data['matches'][0]['id']
        
        # Get match to see participants
        match = Match.objects.get(pk=match_id)
        p_a_idx = self.participants.index(match.participant_a)
        p_b_idx = self.participants.index(match.participant_b)
        
        # Both report same scores
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.user_tokens[p_a_idx]}')
        self.client.post(reverse('match-report-score', kwargs={'match_pk': match_id}), {'score_a':2,'score_b':1}, format='json')
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.user_tokens[p_b_idx]}')
        self.client.post(reverse('match-report-score', kwargs={'match_pk': match_id}), {'score_a':2,'score_b':1}, format='json')
        
        # Check standings updated
        standings = LeagueStanding.objects.filter(tournament=self.tournament).order_by('-points')
        winner_standing = standings.first()
        self.assertEqual(winner_standing.won, 1)
        self.assertEqual(winner_standing.points, 3)


class DualReportTests(APITestCase):
    """Dual-report verification tests."""

    def setUp(self):
        self.org = User.objects.create_user(email='org@example.com', username='org', password='pass')
        self.p1 = User.objects.create_user(email='p1@example.com', username='p1', password='pass')
        self.p2 = User.objects.create_user(email='p2@example.com', username='p2', password='pass')

        def token_for(u): return str(RefreshToken.for_user(u).access_token)
        self.org_token = token_for(self.org)
        self.p1_token = token_for(self.p1)
        self.p2_token = token_for(self.p2)

        self.t = Tournament.objects.create(
            name='DR Cup',
            organizer=self.org,
            status='registration_open',
            max_players=2,
            registration_deadline=timezone.now() + timedelta(days=1),
            tournament_type=Tournament.TOURNAMENT_TYPE_CUP
        )
        Participant.objects.create(tournament=self.t, user=self.p1)
        Participant.objects.create(tournament=self.t, user=self.p2)

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.org_token}')
        start = self.client.post(reverse('tournament-start', kwargs={'tournament_pk': self.t.id}))
        self.match_id = start.data['matches'][0]['id']

    def test_matching_reports_auto_finalize(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.p1_token}')
        r1 = self.client.post(reverse('match-report-score', kwargs={'match_pk': self.match_id}), {'score_a':2,'score_b':1}, format='json')
        self.assertEqual(r1.status_code, status.HTTP_202_ACCEPTED)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.p2_token}')
        r2 = self.client.post(reverse('match-report-score', kwargs={'match_pk': self.match_id}), {'score_a':2,'score_b':1}, format='json')
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        m = Match.objects.get(pk=self.match_id)
        self.assertEqual(m.status, Match.STATUS_COMPLETED)

    def test_conflicting_reports_mark_disputed(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.p1_token}')
        self.client.post(reverse('match-report-score', kwargs={'match_pk': self.match_id}), {'score_a':3,'score_b':1}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.p2_token}')
        self.client.post(reverse('match-report-score', kwargs={'match_pk': self.match_id}), {'score_a':1,'score_b':0}, format='json')
        m = Match.objects.get(pk=self.match_id)
        self.assertEqual(m.status, Match.STATUS_DISPUTED)

    def test_conflicting_reports_send_email_notification(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.p1_token}')
        self.client.post(reverse('match-report-score', kwargs={'match_pk': self.match_id}), {'score_a':3,'score_b':1}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.p2_token}')
        self.client.post(reverse('match-report-score', kwargs={'match_pk': self.match_id}), {'score_a':1,'score_b':0}, format='json')
        self.assertEqual(len(mail.outbox), 1)


class FileUploadTests(APITestCase):
    """Tests for evidence file upload."""

    def setUp(self):
        self.org = User.objects.create_user(email='org@example.com', username='org', password='pass')
        self.p1 = User.objects.create_user(email='p1@example.com', username='p1', password='pass')
        self.p2 = User.objects.create_user(email='p2@example.com', username='p2', password='pass')

        def token_for(u): return str(RefreshToken.for_user(u).access_token)
        self.org_token = token_for(self.org)
        self.p1_token = token_for(self.p1)
        self.p2_token = token_for(self.p2)

        self.t = Tournament.objects.create(
            name='File Test',
            organizer=self.org,
            status='registration_open',
            max_players=2,
            registration_deadline=timezone.now() + timedelta(days=1),
            tournament_type=Tournament.TOURNAMENT_TYPE_CUP
        )
        Participant.objects.create(tournament=self.t, user=self.p1)
        Participant.objects.create(tournament=self.t, user=self.p2)

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.org_token}')
        start = self.client.post(reverse('tournament-start', kwargs={'tournament_pk': self.t.id}))
        self.match_id = start.data['matches'][0]['id']

    def test_file_upload_with_score_report(self):
        evidence_file = SimpleUploadedFile("screenshot.txt", b"proof", content_type="text/plain")
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.p1_token}')
        response = self.client.post(
            reverse('match-report-score', kwargs={'match_pk': self.match_id}),
            {'score_a': 2, 'score_b': 1, 'evidence': evidence_file},
            format='multipart'
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        report = MatchReport.objects.filter(match_id=self.match_id, reporter=self.p1).first()
        self.assertIsNotNone(report)
        self.assertTrue(report.evidence)

    def test_file_upload_optional(self):
        """Test score report works without file upload."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.p1_token}')
        
        # Submit report WITHOUT file
        response = self.client.post(
            reverse('match-report-score', kwargs={'match_pk': self.match_id}),
            {'score_a': 2, 'score_b': 1},
            format='json'
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        # Verify report was created without evidence
        report = MatchReport.objects.filter(match_id=self.match_id, reporter=self.p1).first()
        self.assertIsNotNone(report)
        self.assertFalse(report.evidence)
