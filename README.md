# SmartSaver

SmartSaver is a Django price comparison website with API endpoints and a modern UI for finding better deals and cheaper alternatives.

## Features

- Product search by keyword, category, and brand
- Product price comparison across multiple platforms
- Cheaper alternatives endpoint and UI section
- Django admin for managing products, prices, and alerts
- Seed command with realistic sample data

## Tech

- Django 6
- Django REST Framework
- django-filter
- SQLite (default)

## Quick Start

1. Create and activate a virtual environment.
2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Run migrations:

```powershell
python manage.py makemigrations
python manage.py migrate
```

4. Seed sample data:

```powershell
python manage.py seed_data
```

5. Start the server:

```powershell
python manage.py runserver
```

Open http://127.0.0.1:8000/

## API Endpoints

- `GET /api/search/?q=<query>&category=<category>&brand=<brand>`
- `GET /api/compare/<product_id>/`
- `GET /api/alternatives/<product_id>/`

## Admin Access

Create superuser:

```powershell
python manage.py createsuperuser
```

Then open `/admin/`.

## Notes

- For production, switch to PostgreSQL and configure Redis/Celery.
- Current sample integration uses seeded data for reliable MVP validation.
