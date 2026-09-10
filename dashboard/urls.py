from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="dashboard-index"),
    path("vehicles/<int:pk>/", views.vehicle_panel, name="vehicle-panel"),
]
