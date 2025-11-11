from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from tournaments.models import Tournament
from django.utils import timezone

# Basic API tests for tournaments: create/list/retrieve/update/delete and permissions
class TournamentAPITests(APITestCase):
    def setUp(self):
        User = get_user_model()
        # organizer and another user
        self.organizer = User.objects.create_user(email='org@example.com', username='organizer', password='TestPass123!')
        self.other = User.objects.create_user(email='other@example.com', username='other', password='TestPass123!')

        # helper for access token
        def token_for(user):
            return str(RefreshToken.for_user(user).access_token)

        self.org_token = token_for(self.organizer)
        self.other_token = token_for(self.other)
        self.list_create_url = reverse('tournament-list-create')

    def test_create_tournament_authenticated(self):
        """Authenticated user becomes organizer when creating a tournament."""
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.org_token}')
        data = {
            "name": "Test Cup",
            "description": "desc",
            "tournament_type": Tournament.TOURNAMENT_TYPE_CUP,
            "status": Tournament.STATUS_REGISTRATION_OPEN,
            "max_players": 8,
            "registration_deadline": timezone.now()
        }
        resp = self.client.post(self.list_create_url, data, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Tournament.objects.count(), 1)
        self.assertEqual(Tournament.objects.first().organizer, self.organizer)

    def test_list_and_retrieve_public(self):
        """Anyone can list and retrieve tournaments (public read)."""
        Tournament.objects.create(
            name="Public Cup",
            organizer=self.organizer,
            max_players=16,
            registration_deadline=timezone.now()
        )
        resp = self.client.get(self.list_create_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        pk = resp.data[0]['id']
        resp2 = self.client.get(reverse('tournament-detail', args=[pk]))
        self.assertEqual(resp2.status_code, status.HTTP_200_OK)

    def test_only_organizer_can_modify(self):
        """Only organizer may update/delete their tournament."""
        t = Tournament.objects.create(
            name="Secure Cup",
            organizer=self.organizer,
            max_players=16,
            registration_deadline=timezone.now()
        )
        detail = reverse('tournament-detail', args=[t.id])

        # other user cannot modify
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.other_token}')
        resp = self.client.patch(detail, {"name": "Hacked"}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        resp = self.client.delete(detail)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        # organizer can modify/delete
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.org_token}')
        resp = self.client.patch(detail, {"name": "Updated"}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        resp = self.client.delete(detail)
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
