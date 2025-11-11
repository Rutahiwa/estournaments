from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from .models import Tournament, Participant
from django.utils import timezone
from datetime import timedelta

User = get_user_model()

class ParticipantAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='u@example.com', username='u', password='TestPass123!')
        self.other = User.objects.create_user(email='o@example.com', username='o', password='TestPass123!')
        def token_for(u): return str(RefreshToken.for_user(u).access_token)
        self.token = token_for(self.user)
        self.other_token = token_for(self.other)

        self.tournament = Tournament.objects.create(
            name="Open Cup",
            organizer=self.user,
            status=Tournament.STATUS_REGISTRATION_OPEN,
            tournament_type=Tournament.TOURNAMENT_TYPE_CUP,
            max_players=2,
            registration_deadline=timezone.now() + timedelta(days=1)
        )

    def test_join_and_list_participants(self):
        join = reverse('tournament-join', args=[self.tournament.id])
        list_url = reverse('tournament-participants', args=[self.tournament.id])

        # must authenticate to join
        resp = self.client.post(join)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

        # join successfully
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        resp = self.client.post(join)
        assert resp.status_code == status.HTTP_201_CREATED

        # list participants public
        self.client.credentials()
        resp = self.client.get(list_url)
        assert resp.status_code == status.HTTP_200_OK
        assert len(resp.data) == 1

    def test_capacity_enforced(self):
        # fill slot with other user
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.other_token}')
        resp = self.client.post(reverse('tournament-join', args=[self.tournament.id]))
        assert resp.status_code == status.HTTP_201_CREATED

        # create third user to fill second slot
        third = User.objects.create_user(email='t@example.com', username='t', password='TestPass123!')
        third_token = str(RefreshToken.for_user(third).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {third_token}')
        resp = self.client.post(reverse('tournament-join', args=[self.tournament.id]))
        assert resp.status_code == status.HTTP_201_CREATED

        # now original user cannot join because tournament is full
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        resp = self.client.post(reverse('tournament-join', args=[self.tournament.id]))
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_leave(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')
        self.client.post(reverse('tournament-join', args=[self.tournament.id]))
        resp = self.client.delete(reverse('tournament-leave', args=[self.tournament.id]))
        assert resp.status_code == status.HTTP_204_NO_CONTENT
