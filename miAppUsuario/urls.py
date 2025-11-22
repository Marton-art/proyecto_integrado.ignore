from miAppUsuario import views
from django.urls import path

app_name = 'usuarios'

urlpatterns = [
    path('home/', views.home, name='home'),
    path('crear/', views.create, name='create'),
    path('ver/', views.read, name='read'),
    path('editar/<int:pk>/', views.edit, name='edit'), 
    path('eliminar/<int:pk>/', views.delete, name='delete'),
]