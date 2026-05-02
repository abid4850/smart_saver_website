from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Max, Min, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_POST
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, generics
from rest_framework.response import Response
from rest_framework.views import APIView

from comparisons.models import AlternativeProduct
from comparisons.models import ProductPrice
from users.models import SavedFilter

from .models import Product
from .models import ProductNews
from .serializers import AlternativeProductSerializer
from .serializers import ProductPriceSerializer
from .serializers import ProductSerializer


class ProductSearchAPIView(generics.ListAPIView):
	serializer_class = ProductSerializer
	filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
	filterset_fields = ["brand", "category"]
	ordering_fields = ["name", "brand", "category"]
	ordering = ["name"]

	def get_queryset(self):
		queryset = Product.objects.prefetch_related("prices").all()
		query = self.request.query_params.get("q", "").strip()
		if query:
			queryset = queryset.filter(
				Q(name__icontains=query)
				| Q(brand__icontains=query)
				| Q(category__icontains=query)
			)
		return queryset


class ProductComparisonAPIView(APIView):
	def get(self, request, product_id):
		product = get_object_or_404(Product.objects.prefetch_related("prices"), pk=product_id)
		prices = ProductPrice.objects.filter(product=product).order_by("price", "platform")
		best_deal = prices.first()

		return Response(
			{
				"product": ProductSerializer(product).data,
				"best_deal": ProductPriceSerializer(best_deal).data if best_deal else None,
				"prices": ProductPriceSerializer(prices, many=True).data,
			}
		)


class ProductAlternativesAPIView(APIView):
	def get(self, request, product_id):
		product = get_object_or_404(Product, pk=product_id)
		alternatives = (
			AlternativeProduct.objects.select_related("alternative_product")
			.filter(main_product=product, price_difference__gt=0)
			.order_by("-price_difference", "-similarity_score")
		)

		return Response(
			{
				"product": ProductSerializer(product).data,
				"alternatives": AlternativeProductSerializer(alternatives, many=True).data,
			}
		)


def home_view(request):
	featured_products = Product.objects.prefetch_related("prices").all()[:6]
	latest_news = ProductNews.objects.filter(is_published=True, published_at__lte=timezone.now())[:3]
	return render(request, "home.html", {"featured_products": featured_products, "latest_news": latest_news})


def autocomplete_api(request):
	query = request.GET.get("q", "").strip()
	if len(query) < 2:
		return JsonResponse({"suggestions": []})

	product_names = list(
		Product.objects.filter(name__icontains=query)
		.order_by("name")
		.values_list("name", flat=True)
		.distinct()[:8]
	)
	brands = list(
		Product.objects.filter(brand__icontains=query)
		.order_by("brand")
		.values_list("brand", flat=True)
		.distinct()[:4]
	)
	categories = list(
		Product.objects.filter(category__icontains=query)
		.order_by("category")
		.values_list("category", flat=True)
		.distinct()[:4]
	)

	suggestions = []
	seen = set()
	for value in [*product_names, *brands, *categories]:
		normalized = value.lower()
		if normalized in seen:
			continue
		seen.add(normalized)
		suggestions.append(value)
		if len(suggestions) >= 10:
			break

	return JsonResponse({"suggestions": suggestions})


def _parse_decimal(value):
	if not value:
		return None
	try:
		return Decimal(value)
	except InvalidOperation:
		return None


def _resolve_category_from_slug(category_slug):
	all_categories = Product.objects.order_by().values_list("category", flat=True).distinct()
	for item in all_categories:
		if slugify(item) == category_slug:
			return item
	return ""


def _build_results_context(request, forced_category=""):
	query = request.GET.get("q", "").strip()
	category = forced_category.strip() if forced_category else request.GET.get("category", "").strip()
	brand = request.GET.get("brand", "").strip()
	sort = request.GET.get("sort", "name_asc").strip()
	min_price = _parse_decimal(request.GET.get("min_price", "").strip())
	max_price = _parse_decimal(request.GET.get("max_price", "").strip())

	price_bounds = ProductPrice.objects.aggregate(global_min=Min("price"), global_max=Max("price"))
	price_floor = int(price_bounds["global_min"] or 0)
	price_ceiling = int(price_bounds["global_max"] or 5000)

	if min_price is None:
		min_price = Decimal(price_floor)
	if max_price is None:
		max_price = Decimal(price_ceiling)
	if min_price > max_price:
		min_price, max_price = max_price, min_price

	base_products = Product.objects.prefetch_related("prices").annotate(lowest_price=Min("prices__price"))
	if query:
		base_products = base_products.filter(
			Q(name__icontains=query)
			| Q(brand__icontains=query)
			| Q(category__icontains=query)
		)
	if brand:
		base_products = base_products.filter(brand__icontains=brand)
	base_products = base_products.filter(lowest_price__gte=min_price, lowest_price__lte=max_price)

	category_counts_rows = (
		base_products.values("category")
		.annotate(total=Count("id"))
		.order_by("category")
	)
	category_counts = {row["category"]: row["total"] for row in category_counts_rows}
	category_totals = [
		{
			"name": row["category"],
			"count": row["total"],
			"slug": slugify(row["category"]),
		}
		for row in category_counts_rows
	]
	all_categories_total = sum(item["count"] for item in category_totals)

	products = base_products
	if category:
		products = products.filter(category__icontains=category)

	if sort == "price_low":
		products = products.order_by("lowest_price", "name")
	elif sort == "price_high":
		products = products.order_by("-lowest_price", "name")
	elif sort == "name_desc":
		products = products.order_by("-name")
	else:
		products = products.order_by("name")

	paginator = Paginator(products, 12)
	page_obj = paginator.get_page(request.GET.get("page"))

	query_params = request.GET.copy()
	query_params["category"] = category
	if "page" in query_params:
		query_params.pop("page")
	pagination_query = query_params.urlencode()
	if pagination_query:
		pagination_query = f"&{pagination_query}"

	popular_categories = list(category_counts.keys())
	if not popular_categories:
		popular_categories = list(
			Product.objects.order_by().values_list("category", flat=True).distinct().order_by("category")
		)
	popular_brands = list(
		Product.objects.order_by().values_list("brand", flat=True).distinct().order_by("brand")
	)

	saved_filters = []
	if request.user.is_authenticated:
		raw_filters = SavedFilter.objects.filter(user=request.user)[:12]
		for saved in raw_filters:
			query_data = {
				"q": saved.query,
				"category": saved.category,
				"brand": saved.brand,
				"sort": saved.sort,
				"min_price": saved.min_price,
				"max_price": saved.max_price,
			}
			query_string = urlencode(query_data)
			saved.share_url = f"/results/?{query_string}"
			saved_filters.append(saved)

	return {
		"query": query,
		"category": category,
		"brand": brand,
		"sort": sort,
		"min_price": int(min_price),
		"max_price": int(max_price),
		"price_floor": price_floor,
		"price_ceiling": price_ceiling,
		"products": page_obj.object_list,
		"page_obj": page_obj,
		"paginator": paginator,
		"pagination_query": pagination_query,
		"total_results": paginator.count,
		"all_categories_total": all_categories_total,
		"category_counts": category_counts,
		"category_totals": category_totals,
		"popular_categories": popular_categories,
		"popular_brands": popular_brands,
		"saved_filters": saved_filters,
	}


def _saved_filter_share_url(saved_filter):
	query_data = {
		"q": saved_filter.query,
		"category": saved_filter.category,
		"brand": saved_filter.brand,
		"sort": saved_filter.sort,
		"min_price": saved_filter.min_price,
		"max_price": saved_filter.max_price,
	}
	return f"/results/?{urlencode(query_data)}"


@login_required
def favorites_view(request):
	query = request.GET.get("q", "").strip()
	favorites = SavedFilter.objects.filter(user=request.user, is_pinned=True)
	
	if query:
		favorites = favorites.filter(Q(name__icontains=query) | Q(query__icontains=query))
	
	favorites = list(favorites[:24])
	for saved in favorites:
		saved.share_url = _saved_filter_share_url(saved)

	return render(
		request,
		"favorites.html",
		{
			"favorites": favorites,
			"total_favorites": len(favorites),
			"query": query,
		},
	)


def results_view(request):
	context = _build_results_context(request)
	return render(request, "results.html", context)


def category_results_view(request, category_slug):
	resolved_category = _resolve_category_from_slug(category_slug)
	if not resolved_category:
		raise Http404("Category not found")

	context = _build_results_context(request, forced_category=resolved_category)
	return render(request, "results.html", context)


@login_required
@require_POST
def save_filter_view(request):
	name = request.POST.get("name", "").strip()
	query = request.POST.get("query", "").strip()
	category = request.POST.get("category", "").strip()
	brand = request.POST.get("brand", "").strip()
	sort = request.POST.get("sort", "name_asc").strip() or "name_asc"
	min_price = _parse_decimal(request.POST.get("min_price", "").strip())
	max_price = _parse_decimal(request.POST.get("max_price", "").strip())

	if min_price is None:
		min_price = Decimal("0")
	if max_price is None:
		max_price = Decimal("5000")

	if not name:
		label_seed = query or category or brand or "Smart Filter"
		name = f"{label_seed} ({sort})"

	SavedFilter.objects.update_or_create(
		user=request.user,
		name=name,
		defaults={
			"query": query,
			"category": category,
			"brand": brand,
			"sort": sort,
			"min_price": min_price,
			"max_price": max_price,
		},
	)
	messages.success(request, "Filter saved to your account.")
	return redirect(request.POST.get("next") or "/results/")


@login_required
@require_POST
def delete_filter_view(request, filter_id):
	deleted_count, _ = SavedFilter.objects.filter(user=request.user, id=filter_id).delete()
	if deleted_count:
		messages.success(request, "Saved filter removed.")
	else:
		messages.error(request, "Saved filter not found.")
	return redirect(request.POST.get("next") or "/results/")


@login_required
@require_POST
def toggle_pin_filter_view(request, filter_id):
	filter_obj = get_object_or_404(SavedFilter, user=request.user, id=filter_id)
	filter_obj.is_pinned = not filter_obj.is_pinned
	filter_obj.save(update_fields=["is_pinned", "updated_at"])
	message = "Filter pinned to top." if filter_obj.is_pinned else "Filter unpinned."
	messages.success(request, message)
	return redirect(request.POST.get("next") or "/results/")


def news_list_view(request):
	category = request.GET.get("category", "").strip()
	news_items = ProductNews.objects.filter(is_published=True, published_at__lte=timezone.now())
	
	if category and category in dict(ProductNews.CATEGORY_CHOICES):
		news_items = news_items.filter(news_category=category)
	
	# Get all categories with counts for filtering UI
	all_categories = (
		ProductNews.objects
		.filter(is_published=True, published_at__lte=timezone.now())
		.values_list("news_category", flat=True)
		.distinct()
	)
	category_data = [
		{
			"value": cat,
			"label": dict(ProductNews.CATEGORY_CHOICES).get(cat, cat),
			"count": ProductNews.objects.filter(is_published=True, news_category=cat, published_at__lte=timezone.now()).count(),
		}
		for cat in all_categories
	]
	
	paginator = Paginator(news_items, 9)
	page_obj = paginator.get_page(request.GET.get("page"))
	return render(
		request,
		"news_list.html",
		{
			"news_items": page_obj.object_list,
			"page_obj": page_obj,
			"paginator": paginator,
			"categories": category_data,
			"selected_category": category,
		},
	)


def news_detail_view(request, slug):
	news_item = get_object_or_404(
		ProductNews,
		slug=slug,
		is_published=True,
		published_at__lte=timezone.now(),
	)
	related_news = ProductNews.objects.filter(is_published=True, published_at__lte=timezone.now()).exclude(id=news_item.id)[:3]
	edit_url = None
	if request.user.is_staff:
		edit_url = f"/admin/products/productnews/{news_item.id}/change/"
	return render(
		request,
		"news_detail.html",
		{"news_item": news_item, "related_news": related_news, "edit_url": edit_url},
	)


def product_detail_view(request, product_id):
	product = get_object_or_404(Product.objects.prefetch_related("prices"), pk=product_id)
	prices = ProductPrice.objects.filter(product=product).order_by("price", "platform")
	best_deal = prices.first()
	alternatives = (
		AlternativeProduct.objects.select_related("alternative_product")
		.filter(main_product=product, price_difference__gt=0)
		.order_by("-price_difference", "-similarity_score")
	)

	context = {
		"product": product,
		"prices": prices,
		"best_deal": best_deal,
		"alternatives": alternatives,
	}
	return render(request, "product_detail.html", context)
