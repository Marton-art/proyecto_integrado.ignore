# miAppCalificacion/urls.py

from django.urls import path
from . import views

app_name = 'calificaciones'

urlpatterns = [
    # (CRUD)
    path('', views.calificaciones_home, name='menu'),
    path('listado/', views.list_calificaciones, name='calificacion_list'),
    path('crear/', views.create_calificacion, name='create_calificacion'),
    path('editar/<int:pk>/', views.edit_calificacion, name='edit_calificacion'),
    path('eliminar/<int:pk>/', views.delete_calificacion, name='delete_calificacion'),
    
    # funciones para la carga
    path('carga-masiva/', views.bulk_upload_monto, name='bulk_upload_monto'),
    path('carga-factores/', views.bulk_upload_factor, name='bulk_upload_factor'),

    # url para la vista de acceso denegado
    path('forbidden/', views.forbidden_access, name='forbidden'),
]