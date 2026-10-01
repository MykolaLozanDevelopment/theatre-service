from rest_framework import serializers
from django.db import transaction

from cinema.models import (
    Actor,
    Genre,
    Performance,
    Play,
    Reservation,
    TheatreHall,
    Ticket,
)


class ActorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Actor
        fields = ("id", "first_name", "last_name")


class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = ("id", "name")


class TheatreHallSerializer(serializers.ModelSerializer):
    class Meta:
        model = TheatreHall
        fields = ("id", "name", "rows", "seats_in_row")


class PlaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Play
        fields = ("id", "title", "description", "actors", "genres")


class PlayListSerializer(PlaySerializer):
    actors = serializers.SlugRelatedField(
        many=True, read_only=True, slug_field="last_name"
    )
    genres = serializers.SlugRelatedField(
        many=True, read_only=True, slug_field="name"
    )


class PlayDetailSerializer(PlaySerializer):
    actors = ActorSerializer(many=True, read_only=True)
    genres = GenreSerializer(many=True, read_only=True)


class PerformanceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Performance
        fields = ("id", "play", "theatre_hall", "show_time")


class PerformanceListSerializer(PerformanceSerializer):
    play_title = serializers.CharField(source="play.title", read_only=True)
    theatre_hall_name = serializers.CharField(
        source="theatre_hall.name", read_only=True
    )
    theatre_hall_capacity = serializers.SerializerMethodField()
    tickets_available = serializers.SerializerMethodField()

    class Meta:
        model = Performance
        fields = (
            "id",
            "play_title",
            "theatre_hall_name",
            "theatre_hall_capacity",
            "show_time",
            "tickets_available",
        )

    def get_theatre_hall_capacity(self, obj):
        return obj.theatre_hall.rows * obj.theatre_hall.seats_in_row

    def get_tickets_available(self, obj):
        capacity = obj.theatre_hall.rows * obj.theatre_hall.seats_in_row
        return capacity - obj.tickets.count()


class TicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ticket
        fields = ("id", "row", "seat", "performance")

    def validate(self, attrs):
        data = super().validate(attrs)
        Ticket.validate_seat(
            attrs["row"],
            attrs["seat"],
            attrs["performance"].theatre_hall,
            serializers.ValidationError,
        )
        return data


class TicketListSerializer(TicketSerializer):
    performance = PerformanceListSerializer(read_only=True)


class ReservationSerializer(serializers.ModelSerializer):
    tickets = TicketSerializer(many=True, allow_empty=False)

    class Meta:
        model = Reservation
        fields = ("id", "created_at", "tickets")

    def create(self, validated_data):
        tickets_data = validated_data.pop("tickets")
        with transaction.atomic():
            reservation = Reservation.objects.create(
                user=self.context["request"].user, **validated_data
            )
            for ticket_data in tickets_data:
                Ticket.objects.create(reservation=reservation, **ticket_data)
        return reservation


class ReservationListSerializer(ReservationSerializer):
    tickets = TicketListSerializer(many=True, read_only=True)
