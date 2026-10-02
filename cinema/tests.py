from datetime import datetime, timezone

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from cinema.models import (
    Actor,
    Genre,
    Performance,
    Play,
    TheatreHall,
    Ticket,
)

PLAY_URL = reverse("cinema:play-list")
PERFORMANCE_URL = reverse("cinema:performance-list")
RESERVATION_URL = reverse("cinema:reservation-list")


def sample_theatre_hall(**params):
    defaults = {"name": "Main Hall", "rows": 10, "seats_in_row": 15}
    defaults.update(params)
    return TheatreHall.objects.create(**defaults)


def sample_play(**params):
    defaults = {"title": "Hamlet", "description": "A tragedy by Shakespeare"}
    defaults.update(params)
    return Play.objects.create(**defaults)


def sample_performance(**params):
    defaults = {
        "play": sample_play(),
        "theatre_hall": sample_theatre_hall(),
        "show_time": datetime(2026, 12, 1, 19, 0, tzinfo=timezone.utc),
    }
    defaults.update(params)
    return Performance.objects.create(**defaults)


class TicketModelTests(TestCase):
    def test_validate_seat_within_range_does_not_raise(self):
        theatre_hall = sample_theatre_hall(rows=5, seats_in_row=10)
        Ticket.validate_seat(3, 7, theatre_hall, ValueError)

    def test_validate_seat_row_out_of_range_raises(self):
        theatre_hall = sample_theatre_hall(rows=5, seats_in_row=10)
        with self.assertRaises(ValueError):
            Ticket.validate_seat(6, 7, theatre_hall, ValueError)

    def test_validate_seat_seat_out_of_range_raises(self):
        theatre_hall = sample_theatre_hall(rows=5, seats_in_row=10)
        with self.assertRaises(ValueError):
            Ticket.validate_seat(3, 11, theatre_hall, ValueError)


class UnauthenticatedCinemaApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_auth_required_for_plays(self):
        res = self.client.get(PLAY_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_auth_required_for_reservations(self):
        res = self.client.get(RESERVATION_URL)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class AuthenticatedCinemaApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="user", password="testpass123"
        )
        self.client.force_authenticate(self.user)

    def test_list_plays(self):
        sample_play(title="Hamlet")
        sample_play(title="Macbeth")

        res = self.client.get(PLAY_URL)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 2)

    def test_filter_plays_by_title(self):
        sample_play(title="Hamlet")
        sample_play(title="Macbeth")

        res = self.client.get(PLAY_URL, {"title": "ham"})

        self.assertEqual(len(res.data), 1)
        self.assertEqual(res.data[0]["title"], "Hamlet")

    def test_filter_performances_by_date(self):
        sample_performance(
            show_time=datetime(2026, 12, 1, 19, 0, tzinfo=timezone.utc)
        )
        sample_performance(
            show_time=datetime(2026, 12, 2, 19, 0, tzinfo=timezone.utc)
        )

        res = self.client.get(PERFORMANCE_URL, {"date": "2026-12-01"})

        self.assertEqual(len(res.data), 1)

    def test_staff_can_create_play(self):
        self.user.is_staff = True
        self.user.save()
        actor = Actor.objects.create(first_name="John", last_name="Doe")
        genre = Genre.objects.create(name="Drama")
        payload = {
            "title": "Othello",
            "description": "Another tragedy",
            "actors": [actor.id],
            "genres": [genre.id],
        }

        res = self.client.post(PLAY_URL, payload)

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Play.objects.filter(title="Othello").exists())


class ReservationApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="user", password="testpass123"
        )
        self.client.force_authenticate(self.user)
        self.performance = sample_performance()

    def test_create_reservation_with_tickets(self):
        payload = {
            "tickets": [
                {"row": 1, "seat": 1, "performance": self.performance.id},
                {"row": 1, "seat": 2, "performance": self.performance.id},
            ]
        }

        res = self.client.post(RESERVATION_URL, payload, format="json")

        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Ticket.objects.count(), 2)

    def test_reservation_is_linked_to_current_user(self):
        payload = {
            "tickets": [
                {"row": 1, "seat": 1, "performance": self.performance.id}
            ]
        }

        res = self.client.post(RESERVATION_URL, payload, format="json")

        reservation_id = res.data["id"]
        reservation = self.user.reservations.get(id=reservation_id)
        self.assertEqual(reservation.user, self.user)

    def test_cannot_book_seat_out_of_range(self):
        payload = {
            "tickets": [
                {"row": 999, "seat": 1, "performance": self.performance.id}
            ]
        }

        res = self.client.post(RESERVATION_URL, payload, format="json")

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cannot_book_already_taken_seat(self):
        Ticket.objects.create(
            row=1,
            seat=1,
            performance=self.performance,
            reservation=self.user.reservations.create(),
        )
        payload = {
            "tickets": [
                {"row": 1, "seat": 1, "performance": self.performance.id}
            ]
        }

        res = self.client.post(RESERVATION_URL, payload, format="json")

        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_user_sees_only_own_reservations(self):
        other_user = User.objects.create_user(
            username="other", password="testpass123"
        )
        other_user.reservations.create()
        self.user.reservations.create()

        res = self.client.get(RESERVATION_URL)

        self.assertEqual(res.data["count"], 1)
