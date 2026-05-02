from rest_framework import serializers

from comparisons.models import AlternativeProduct, ProductPrice

from .models import Product


class ProductSerializer(serializers.ModelSerializer):
    cheapest_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    cheapest_platform = serializers.CharField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "brand",
            "category",
            "description",
            "image_url",
            "cheapest_price",
            "cheapest_platform",
        ]


class ProductPriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductPrice
        fields = ["id", "platform", "price", "product_url", "last_updated"]


class AlternativeProductSerializer(serializers.ModelSerializer):
    alternative_product = ProductSerializer(read_only=True)

    class Meta:
        model = AlternativeProduct
        fields = [
            "id",
            "alternative_product",
            "similarity_score",
            "price_difference",
        ]