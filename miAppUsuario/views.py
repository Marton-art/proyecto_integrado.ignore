# miAppUsuario/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from datetime import timedelta 
from django.contrib.auth import login, logout, authenticate
from django.contrib import messages 
from django.contrib.auth.hashers import make_password, check_password 
from django.contrib.auth.decorators import login_required
import pandas as pd 
from django.db import IntegrityError

from .models import Usuario, Rol
from miAppCalificacion.models import Pais
from .forms import UsuarioForm

def home(request):
    siete_dias_atras = timezone.now() - timedelta(days=7)
    total_registros = Usuario.objects.count()
    
    registros_recientes = Usuario.objects.filter(
        fecha_creacion__gte=siete_dias_atras
    ).count()

    usuarios_activos = Usuario.objects.filter(is_active=True).count()
    
    context = {
        'total_registros': total_registros,
        'registros_recientes': registros_recientes,
        'usuarios_activos': usuarios_activos
    }
    
    return render(request, 'home.html', context)


def create(request):
    if request.method == "POST":

        if 'excel_file' in request.FILES and request.POST.get('bulk_upload') == 'true':
            excel_file = request.FILES['excel_file']
            
            if not excel_file.name.endswith(('.xlsx', '.xls')):
                messages.error(request, 'El archivo debe ser de formato Excel (.xlsx o .xls).')
                return redirect('usuarios:create')
            
            try:
                df = pd.read_excel(excel_file)
                df = df.fillna('')
                
                columnas_esperadas = ['nombre', 'apellido', 'email', 'telefono', 'edad', 'rol_id', 'pais_id', 'contraseña']
                
                if not all(col in df.columns for col in columnas_esperadas):
                    messages.error(request, 'El archivo Excel debe contener las columnas: nombre, apellido, email, telefono, edad, rol_id, pais_id, contraseña.')
                    return redirect('usuarios:create')

                usuarios_creados = 0
                errores = []
                
                for index, row in df.iterrows():
                    try:
                        rol_obj = Rol.objects.get(pk=row['rol_id'])
                        pais_obj = Pais.objects.get(pk=row['pais_id'])
                        

                        nuevo_usuario = Usuario(
                            first_name=row['nombre'],
                            last_name=row['apellido'],
                            email=row['email'],
                            telefono=row['telefono'],
                            edad=row['edad'],
                            rol_usuario=rol_obj,
                            pais_usuario=pais_obj,
                            is_active=True, 
                            fecha_creacion=timezone.now()
                        )
                        
                        nuevo_usuario.set_password(row['contraseña'])
                        
                        nuevo_usuario.save()
                        
                        usuarios_creados += 1
                        
                    except Rol.DoesNotExist:
                        errores.append(f"Fila {index + 2}: El Rol con ID {row['rol_id']} no existe.")
                    except Pais.DoesNotExist:
                        errores.append(f"Fila {index + 2}: El País con ID {row['pais_id']} no existe.")
                    except IntegrityError:
                        errores.append(f"Fila {index + 2}: Error de integridad (ej. email duplicado) para {row['email']}.")
                    except Exception as e:
                        errores.append(f"Fila {index + 2}: Error desconocido al crear usuario. {e}")
                

                if usuarios_creados > 0:
                    messages.success(request, f'Carga masiva exitosa: {usuarios_creados} usuarios creados.')
                
                if errores:
                    error_msg = f'Se crearon {usuarios_creados} usuarios. {len(errores)} errores encontrados: '
                    for i, error in enumerate(errores):
                        if i < 5:
                            error_msg += f'({error}) '
                        else:
                            error_msg += f'...y {len(errores) - 5} errores más.'
                            break
                    messages.error(request, error_msg)

                return redirect('usuarios:read')
            
            except Exception as e:
                messages.error(request, f'Error al procesar el archivo Excel: {e}')
                return redirect('usuarios:create')
                
        form = UsuarioForm(request.POST)
        
        if form.is_valid():
            usuario = form.save(commit=False)
            password = form.cleaned_data.get('contraseña')
            
            usuario.set_password(password)
            
            usuario.save()
            
            messages.success(request, 'Usuario creado exitosamente. Puede verlo en la lista de registros.')
            
            return redirect('usuarios:read')
        else:
            messages.error(request, 'Error al crear el usuario. Por favor, revise los campos marcados.')
    else:
        form = UsuarioForm()

    siete_dias_atras = timezone.now() - timedelta(days=7)
    total_registros = Usuario.objects.count()
    
    registros_recientes = Usuario.objects.filter(
        fecha_creacion__gte=siete_dias_atras
    ).count()

    usuarios_activos = Usuario.objects.filter(is_active=True).count()
    context = {
        'form': form,
        'usuarios': Usuario.objects.all(),
        'total_registros': total_registros,
        'registros_recientes': registros_recientes,
        'usuarios_activos': usuarios_activos
    }
    return render(request, 'create.html', context)

def read(request):
    """Muestra todos los registros de usuarios en una tabla."""
    usuarios = Usuario.objects.select_related('pais_usuario').all()
    siete_dias_atras = timezone.now() - timedelta(days=7)
    
    context = {
        'usuarios': usuarios,
        'total_registros': Usuario.objects.count(),
        'registros_recientes': Usuario.objects.filter(fecha_creacion__gte=siete_dias_atras).count(),
        'usuarios_activos': Usuario.objects.filter(is_active=True).count()
    }
    
    return render(request, 'read.html', context)

def edit(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)

    if request.method == "POST":
        form = UsuarioForm(request.POST, instance=usuario)
        
        if form.is_valid():
            usuario_instance = form.save(commit=False)
            password = form.cleaned_data.get('contraseña')
            
            if password:
                usuario_instance.set_password(password)

            usuario_instance.save()
            messages.success(request, f'¡El usuario "{usuario.first_name} {usuario.last_name}" ha sido actualizado exitosamente!') 
            
            return redirect('usuarios:read')
        else:
            messages.error(request, 'Error al actualizar el usuario. Por favor, revise los campos marcados.')
    
    else:
        form = UsuarioForm(instance=usuario)
    siete_dias_atras = timezone.now() - timedelta(days=7)
    
    context = {
        'form': form,
        'usuario': usuario,
        'total_registros': Usuario.objects.count(),
        'registros_recientes': Usuario.objects.filter(fecha_creacion__gte=siete_dias_atras).count(),
        'usuarios_activos': Usuario.objects.filter(is_active=True).count()
    }
    
    return render(request, 'edit.html', context)

def delete(request, pk):
    usuario = get_object_or_404(Usuario, pk=pk)
    if request.method == "POST":
        nombre_completo = f"{usuario.first_name} {usuario.last_name}"
        
        try:
            usuario.delete()
            messages.success(request, f'¡El usuario "{nombre_completo}" ha sido **eliminado permanentemente** del sistema!')
            return redirect('usuarios:read')
            
        except Exception as e:
            messages.error(request, f'Error al intentar eliminar el usuario "{nombre_completo}". Detalle: {e}')
            return redirect('usuarios:read')
        
    siete_dias_atras = timezone.now() - timedelta(days=7)
    
    context = {
        'usuario': usuario,
        'total_registros': Usuario.objects.count(),
        'registros_recientes': Usuario.objects.filter(fecha_creacion__gte=siete_dias_atras).count(),
        'usuarios_activos': Usuario.objects.filter(is_active=True).count()
    }
    return render(request, 'delete.html', context)

def login_view(request):
    if request.user.is_authenticated:
        return redirect('admin_dashboard')

    if request.method == 'POST':
        email_ingresado = request.POST.get('email')
        password_ingresada = request.POST.get('contraseña')
        usuario = authenticate(request, email=email_ingresado, password=password_ingresada)
        
        if usuario is not None:
            if usuario.is_active:
                login(request, usuario)
                messages.success(request, '¡Inicio de sesión exitoso!')
                return redirect('admin_dashboard') 
            else:
                messages.error(request, 'Su cuenta está inactiva. Contacte al administrador.')
                
        else:
            messages.error(request, 'Credenciales inválidas. Revise su email y contraseña.')
            
    return render(request, 'login.html')


@login_required(login_url='login') 
def admin_dashboard(request):
    rol_actual = request.user.rol_usuario.nombre if hasattr(request.user, 'rol_usuario') and request.user.rol_usuario else None
    
    if rol_actual == 'Administrador':
        context = {
            'nombre_usuario': request.user.first_name, 
            'rol': rol_actual,
        }
        return render(request, 'admin-dashboard.html', context) 
        
    else:
        messages.warning(request, f'Acceso denegado. Su rol ({rol_actual if rol_actual else "No definido"}) no está autorizado para esta área.')
        logout(request)
        return redirect('login')

def logout_view(request):
    logout(request)
    messages.success(request, 'Has cerrado sesión exitosamente.')
    return redirect('login')