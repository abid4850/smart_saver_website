from django.contrib import admin

from .models import Product
from .models import ProductNews


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
	list_display = ("name", "brand", "category")
	search_fields = ("name", "brand", "category")
	list_filter = ("category", "brand")


@admin.register(ProductNews)
class ProductNewsAdmin(admin.ModelAdmin):
	list_display = ("title", "news_category", "product", "is_published", "published_at")
	search_fields = ("title", "summary", "product__name")
	list_filter = ("is_published", "news_category", "published_at")
	prepopulated_fields = {"slug": ("title",)}
