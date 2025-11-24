from django.contrib.auth import get_user_model

# -----------------------------------------------
# FUNCIONES DE VERIFICACIÓN INDIVIDUAL
# -----------------------------------------------

def is_admin(user):
    """Verifica si el usuario tiene el rol de Administrador."""
    if not user.is_authenticated:
        return False
    return user.rol.nombre == 'Administrador'

def is_analista(user):
    """Verifica si el usuario es Analista o Contador (encargado del ingreso)."""
    # Asume que los roles de ingreso son 'Analista' o 'Contador'
    return user.is_authenticated and user.rol.nombre in ['Analista', 'Contador']

def is_gerente(user):
    """Verifica si el usuario es Gerente o Validador (encargado de la aprobación)."""
    # Asume que el rol de revisión/aprobación es 'Gerente'
    return user.is_authenticated and user.rol.nombre == 'Gerente'

# -----------------------------------------------
# FUNCIONES DE VERIFICACIÓN COMBINADA
# -----------------------------------------------

def has_access(user, required_roles):
    """Verifica si el usuario pertenece a la lista de roles requeridos o es Administrador."""
    if not user.is_authenticated:
        return False
    
    # El Administrador tiene acceso total a todo
    if user.rol.nombre == 'Administrador':
        return True
        
    return user.rol.nombre in required_roles