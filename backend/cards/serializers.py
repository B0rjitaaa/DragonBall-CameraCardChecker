from rest_framework import serializers

from .models import Card


class CardSerializer(serializers.ModelSerializer):
    class Meta:
        model = Card
        fields = [
            "id",
            "bandai_id",
            "card_number",
            "name",
            "set_code",
            "set_name",
            "rarity",
            "card_type",
            "color",
            "cost",
            "power",
            "text",
            "image_url",
            "back_name",
            "back_text",
            "image_back_url",
            "attributes",
        ]


class CardSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = Card
        fields = ["id", "bandai_id", "card_number", "name", "set_code", "rarity", "color", "image_url"]
