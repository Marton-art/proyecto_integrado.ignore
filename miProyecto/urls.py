"""
URL configuration for miProyecto project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path,include
from miAppUsuario import views
from django.contrib.auth.decorators import user_passes_test
from miAppUsuario.utils import is_admin
urlpatterns = [
    path('admin/', user_passes_test(is_admin, login_url='/calificaciones/menu/')(admin.site.urls)),
    path('usuarios/', include('miAppUsuario.urls', namespace='usuarios')),
    path('', views.login_view, name='login'), 
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('logout/', views.logout_view, name='logout'),
    path('miAppCalificacion/',include('miAppCalificacion.urls', namespace='calificaciones')),
]
