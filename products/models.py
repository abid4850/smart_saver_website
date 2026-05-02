from django.db import models
from django.utils.text import slugify


class Product(models.Model):
	name = models.CharField(max_length=255, db_index=True)
	brand = models.CharField(max_length=120, db_index=True)
	category = models.CharField(max_length=120, db_index=True)
	description = models.TextField(blank=True)
	image_url = models.URLField(blank=True)
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["name"]

	def __str__(self) -> str:
		return f"{self.brand} {self.name}".strip()

	@property
	def cheapest_price(self):
		cheapest = self.prices.order_by("price").first()
		return cheapest.price if cheapest else None

	@property
	def cheapest_platform(self):
		cheapest = self.prices.order_by("price").first()
		return cheapest.platform if cheapest else None


class ProductNews(models.Model):
	CATEGORY_CHOICES = [
		("launches", "Product Launches"),
		("pricing", "Price Updates"),
		("deals", "Hot Deals"),
		("tech", "Technology & Features"),
		("reviews", "Reviews & Analysis"),
		("general", "General News"),
	]
	
	title = models.CharField(max_length=220)
	slug = models.SlugField(max_length=240, unique=True, blank=True)
	summary = models.TextField()
	body = models.TextField(blank=True)
	image_url = models.URLField()
	news_category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default="general", db_index=True)
	product = models.ForeignKey(Product, on_delete=models.SET_NULL, null=True, blank=True, related_name="news_items")
	is_published = models.BooleanField(default=True)
	published_at = models.DateTimeField()
	created_at = models.DateTimeField(auto_now_add=True)
	updated_at = models.DateTimeField(auto_now=True)

	class Meta:
		ordering = ["-published_at"]

	def save(self, *args, **kwargs):
		if not self.slug:
			base_slug = slugify(self.title) or "news-item"
			slug = base_slug
			counter = 2
			while ProductNews.objects.filter(slug=slug).exclude(pk=self.pk).exists():
				slug = f"{base_slug}-{counter}"
				counter += 1
			self.slug = slug
		super().save(*args, **kwargs)

	def __str__(self):
		return self.title
