from django.contrib.auth import get_user_model
from .models import Usuario
# -----------------------------------------------
# FUNCIONES DE VERIFICACIÓN INDIVIDUAL
# -----------------------------------------------

def is_admin(user):
    """Verifica si el usuario tiene el rol de Administrador."""
    if not user.is_authenticated:
        return False
    return user.rol_usuario.nombre == 'Administrador'

def is_analista(user):
    """Verifica si el usuario es Analista o Contador (encargado del ingreso)."""
    # Asume que los roles de ingreso son 'Analista' o 'Contador'
    return user.is_authenticated and user.rol_usuario.nombre in ['Analista', 'Contador']

def is_gerente(user):
    """Verifica si el usuario es Gerente o Validador (encargado de la aprobación)."""
    # Asume que el rol de revisión/aprobación es 'Gerente'
    return user.is_authenticated and user.rol_usuario.nombre == 'Gerente'


# miAppUsuario/utils.py

from .models import Usuario # Importa el modelo de usuario

def has_access(user, required_roles):
    # 1. Si el usuario no está autenticado o es anónimo, retornar False.
    if not user.is_authenticated:
        return False

    # 2. Forzar la recarga del usuario con la relación 'rol'
    #    Esto resuelve el error 'Usuario object has no attribute rol'
    try:
        # Usa select_related('rol') para cargar la relación FK.
        user = Usuario.objects.select_related('rol_usuario').get(pk=user.pk)
    except Usuario.DoesNotExist:
        return False # El usuario no existe

    # 3. Lógica de verificación: verificar si el rol del usuario está en la lista de roles requeridos
    #    Si el usuario es superusuario (is_staff o is_superuser), otorgar acceso total.
    if user.is_staff or user.is_superuser:
        return True

    # 4. Chequear el rol
    if user.rol_usuario and user.rol_usuario.nombre in required_roles:
        return True
        
    return False

# Nota: Asegúrate de que tu modelo Usuario sea importado correctamente
# y que el campo 'rol' apunte a tu modelo 'Rol'.