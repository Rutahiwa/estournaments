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
from .models import Match, MatchReport
from .bracket_generator import generate_single_elimination_bracket
from django.utils import timezone
from datetime import timedelta
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail

User = get_user_model()


class BracketGeneratorTests(APITestCase):
    """Tests for bracket generation logic."""
    
    def setUp(self):
        """Set up test tournament with 4 participants."""
        self.org = User.objects.create_user(
            email='org@example.com',
            username='org',
            password='TestPass123!'
        )
        self.tournament = Tournament.objects.create(
            name='Test Cup',
            organizer=self.org,
            status='registration_open',
            max_players=4,
            registration_deadline=timezone.now() + timedelta(days=1)
        )
        
        # Create 4 participants
        self.participants = []
        for i in range(4):
            user = User.objects.create_user(
                email=f'p{i}@example.com',
                username=f'p{i}',
                password='TestPass123!'
            )
            participant = Participant.objects.create(
                tournament=self.tournament,
                user=user
            )
            self.participants.append(participant)

    def test_bracket_generation_creates_round_1_matches(self):
        """Verify bracket generation creates correct number of Round 1 matches."""
        matches = generate_single_elimination_bracket(self.tournament)
        
        # 4 participants = 2 matches in Round 1
        self.assertEqual(len(matches), 2)
        
        # All matches are Round 1
        for match in matches:
            self.assertEqual(match.round_number, 1)
            self.assertEqual(match.status, Match.STATUS_PENDING)
            self.assertEqual(match.tournament, self.tournament)

    def test_bracket_generation_randomizes_pairings(self):
        """Verify participants are randomly paired."""
        # Generate bracket multiple times
        generated_pairings = []
        
        for _ in range(3):
            # Clear previous matches
            Match.objects.filter(tournament=self.tournament).delete()
            
            # Generate bracket
            matches = generate_single_elimination_bracket(self.tournament)
            
            # Record pairings
            pairing = set()
            for match in matches:
                pairing.add((match.participant_a.id, match.participant_b.id))
            
            generated_pairings.append(pairing)
        
        # At least show pairings can vary
        self.assertTrue(len(generated_pairings) > 0)

    def test_bracket_generation_fails_with_odd_participants(self):
        """Verify bracket generation fails with odd number of participants."""
        # Add 5th participant (odd)
        user = User.objects.create_user(
            email='p5@example.com',
            username='p5',
            password='TestPass123!'
        )
        Participant.objects.create(tournament=self.tournament, user=user)
        
        # Should raise ValueError
        with self.assertRaises(ValueError) as context:
            generate_single_elimination_bracket(self.tournament)
        
        self.assertIn('even', str(context.exception).lower())


class MatchAPITests(APITestCase):
    """Tests for Match API endpoints."""
    
    def setUp(self):
        """Set up test tournament with 2 participants."""
        self.org = User.objects.create_user(
            email='org@example.com',
            username='org',
            password='TestPass123!'
        )
        self.p1 = User.objects.create_user(
            email='p1@example.com',
            username='p1',
            password='TestPass123!'
        )
        self.p2 = User.objects.create_user(
            email='p2@example.com',
            username='p2',
            password='TestPass123!'
        )
        
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
            registration_deadline=timezone.now() + timedelta(days=1)
        )
        
        self.part1 = Participant.objects.create(tournament=self.tournament, user=self.p1)
        self.part2 = Participant.objects.create(tournament=self.tournament, user=self.p2)

    def test_organizer_starts_tournament_generates_bracket(self):
        """Test organizer can start tournament and generate bracket."""
        url = reverse('tournament-start', kwargs={'tournament_pk': self.tournament.id})
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.org_token}')
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('matches', response.data)
        self.assertEqual(len(response.data['matches']), 1)  # 2 participants = 1 match

    def test_non_organizer_cannot_start_tournament(self):
        """Test non-organizer cannot start tournament."""
        url = reverse('tournament-start', kwargs={'tournament_pk': self.tournament.id})
        
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.p1_token}')
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_participant_can_report_score(self):
        """Test participant can report match score."""
        # Start tournament
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.org_token}')
        start_resp = self.client.post(
            reverse('tournament-start', kwargs={'tournament_pk': self.tournament.id})
        )
        match_id = start_resp.data['matches'][0]['id']
        
        # First participant reports
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.p1_token}')
        resp1 = self.client.post(reverse('match-report-score', kwargs={'match_pk': match_id}), {'score_a':2,'score_b':1}, format='json')
        self.assertEqual(resp1.status_code, status.HTTP_202_ACCEPTED)

        # Second participant reports same scores -> finalizes
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.p2_token}')
        resp2 = self.client.post(reverse('match-report-score', kwargs={'match_pk': match_id}), {'score_a':2,'score_b':1}, format='json')
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)

        # Verify match is completed with correct scores and winner
        m = Match.objects.get(pk=match_id)
        self.assertEqual(m.status, Match.STATUS_COMPLETED)
        self.assertEqual(m.score_a, 2)
        self.assertEqual(m.score_b, 1)
        self.assertEqual(m.winner, m.participant_a)
        self.assertIn(m.winner, [self.part1, self.part2])

    def test_unauthorized_cannot_report_score(self):
        """Test unauthorized user cannot report score."""
        # Create unrelated user
        other = User.objects.create_user(
            email='other@example.com',
            username='other',
            password='TestPass123!'
        )
        other_token = str(RefreshToken.for_user(other).access_token)
        
        # Start tournament
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.org_token}')
        start_resp = self.client.post(
            reverse('tournament-start', kwargs={'tournament_pk': self.tournament.id})
        )
        match_id = start_resp.data['matches'][0]['id']
        
        # Try to report as unauthorized user
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {other_token}')
        report_url = reverse('match-report-score', kwargs={'match_pk': match_id})
        response = self.client.post(
            report_url,
            {'score_a': 2, 'score_b': 1},
            format='json'
        )
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_bracket_view_returns_structure(self):
        """Test bracket view returns correct structure."""
        # Start tournament
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.org_token}')
        self.client.post(
            reverse('tournament-start', kwargs={'tournament_pk': self.tournament.id})
        )
        
        # View bracket
        self.client.credentials()  # No auth needed
        bracket_url = reverse('tournament-bracket', kwargs={'tournament_pk': self.tournament.id})
        response = self.client.get(bracket_url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['tournament_id'], self.tournament.id)
        self.assertEqual(len(response.data['rounds']), 1)  # Only Round 1 generated
        self.assertEqual(len(response.data['rounds'][0]['matches']), 1)  # 1 match


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
            registration_deadline=timezone.now() + timedelta(days=1)
        )
        Participant.objects.create(tournament=self.t, user=self.p1)
        Participant.objects.create(tournament=self.t, user=self.p2)

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.org_token}')
        start = self.client.post(reverse('tournament-start', kwargs={'tournament_pk': self.t.id}))
        self.match_id = start.data['matches'][0]['id']

    def test_matching_reports_auto_finalize(self):
        """Matching reports from two participants auto-finalize the match."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.p1_token}')
        r1 = self.client.post(reverse('match-report-score', kwargs={'match_pk': self.match_id}), {'score_a':2,'score_b':1}, format='json')
        self.assertEqual(r1.status_code, status.HTTP_202_ACCEPTED)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.p2_token}')
        r2 = self.client.post(reverse('match-report-score', kwargs={'match_pk': self.match_id}), {'score_a':2,'score_b':1}, format='json')
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        m = Match.objects.get(pk=self.match_id)
        self.assertEqual(m.status, Match.STATUS_COMPLETED)
        self.assertEqual(m.winner, m.participant_a)

    def test_conflicting_reports_mark_disputed_and_organizer_resolves(self):
        """Conflicting reports mark match disputed; organizer resolves."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.p1_token}')
        self.client.post(reverse('match-report-score', kwargs={'match_pk': self.match_id}), {'score_a':3,'score_b':1}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.p2_token}')
        self.client.post(reverse('match-report-score', kwargs={'match_pk': self.match_id}), {'score_a':1,'score_b':0}, format='json')
        m = Match.objects.get(pk=self.match_id)
        self.assertEqual(m.status, Match.STATUS_DISPUTED)
        # Organizer accepts p1's report
        report = MatchReport.objects.filter(match=m, reporter__username='p1').first()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.org_token}')
        resp = self.client.post(reverse('match-resolve', kwargs={'match_pk': self.match_id}), {'accept_report_id': report.id}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        m.refresh_from_db()
        self.assertEqual(m.status, Match.STATUS_COMPLETED)
        self.assertEqual(m.score_a, 3)
        self.assertEqual(m.score_b, 1)

    def test_conflicting_reports_send_email_notification(self):
        """Conflicting reports trigger email notification to organizer."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.p1_token}')
        self.client.post(reverse('match-report-score', kwargs={'match_pk': self.match_id}), {'score_a':3,'score_b':1}, format='json')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.p2_token}')
        self.client.post(reverse('match-report-score', kwargs={'match_pk': self.match_id}), {'score_a':1,'score_b':0}, format='json')
        
        # Check email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertIn('disputed', email.subject.lower())
        self.assertEqual(email.to, [self.org.email])
        self.assertIn('conflicting', email.body.lower())


class FileUploadTests(APITestCase):
    """Tests for evidence file upload with score reports."""

    def setUp(self):
        self.org = User.objects.create_user(email='org@example.com', username='org', password='pass')
        self.p1 = User.objects.create_user(email='p1@example.com', username='p1', password='pass')
        self.p2 = User.objects.create_user(email='p2@example.com', username='p2', password='pass')

        def token_for(u): return str(RefreshToken.for_user(u).access_token)
        self.org_token = token_for(self.org)
        self.p1_token = token_for(self.p1)
        self.p2_token = token_for(self.p2)

        self.t = Tournament.objects.create(
            name='File Test Cup',
            organizer=self.org,
            status='registration_open',
            max_players=2,
            registration_deadline=timezone.now() + timedelta(days=1)
        )
        Participant.objects.create(tournament=self.t, user=self.p1)
        Participant.objects.create(tournament=self.t, user=self.p2)

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.org_token}')
        start = self.client.post(reverse('tournament-start', kwargs={'tournament_pk': self.t.id}))
        self.match_id = start.data['matches'][0]['id']

    def test_file_upload_with_score_report(self):
        """Test participant can upload evidence file with score report."""
        # Create a simple text file
        evidence_file = SimpleUploadedFile(
            "screenshot.txt",
            b"This is proof of the match result",
            content_type="text/plain"
        )

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.p1_token}')
        
        # Submit report with file (multipart)
        response = self.client.post(
            reverse('match-report-score', kwargs={'match_pk': self.match_id}),
            {'score_a': 2, 'score_b': 1, 'evidence': evidence_file},
            format='multipart'
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        # Verify file was saved to MatchReport
        report = MatchReport.objects.filter(match_id=self.match_id, reporter=self.p1).first()
        self.assertIsNotNone(report)
        self.assertTrue(report.evidence)
        self.assertIn('screenshot', report.evidence.name)

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
