from django.db import models
from django.contrib.auth.hashers import make_password, check_password
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import AbstractUser, BaseUserManager
class UsuarioManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('El email debe ser establecido.')
        
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')
        
        return self.create_user(email, password, **extra_fields)

class Usuario(AbstractUser):
    username = None
    edad = models.PositiveBigIntegerField(null = True, blank = True)
    email = models.EmailField(max_length=254, unique = True)
    telefono = models.CharField(max_length=30,blank=True, null=True , unique=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True, null=True)

    USERNAME_FIELD = 'email' 
    def has_perm(self, perm, obj=None):
        "Does the user have a specific permission?"
        return self.is_superuser

    def has_module_perms(self, app_label):
        "Does the user have permissions to view the app 'app_label'?"
        return self.is_superuser
    
    objects = UsuarioManager()
    REQUIRED_FIELDS = ['first_name', 'last_name', 'rol_usuario_id', 'pais_usuario_id']
    rol_usuario = models.ForeignKey(
        'Rol',
        on_delete = models.CASCADE,
        related_name = "usuarios_rol",
        verbose_name = "Rol del Sistema"
    )
    pais_usuario = models.ForeignKey(
        'miAppCalificacion.Pais',
        on_delete=models.PROTECT,
        related_name="usuarios_del_pais",
        verbose_name="País de Usuario"
    )
    
    
    def set_clave_secreta(self, clave_raw):
        self.set_password(clave_raw)
        
    def check_clave_secreta(self, clave_raw):
        return self.check_password(clave_raw)	

    class Meta:
        ordering = ['first_name'] 
    def __str__(self):
        return f"{self.nombre} {self.apellido} <{self.email}>"
    
class Auditoria(models.Model):
    STATUS_PENDING = 'PENDING'
    STATUS_VALIDATED = 'VALIDATED'
    STATUS_IMPORTING = 'IMPORTING'
    STATUS_IMPORTED = 'IMPORTED'
    STATUS_CANCELLED = 'CANCELLED'
    STATUS_FAILED = 'FAILED'

    STATUS_CHOICES = [
        (STATUS_PENDING,'Cargando'),
        (STATUS_VALIDATED, 'Calidando (esperando de validacion)'),
        (STATUS_IMPORTING, 'Importando.....'),
        (STATUS_IMPORTED, 'Importado'),
        (STATUS_CANCELLED, 'Proceso cancelado'),
        (STATUS_FAILED, 'Cago mano')
    ]
    uploaded_at = models.DateTimeField(default=timezone.now)
    file = models.FileField(upload_to='imports/', null=True, blank=True)
    filename = models.CharField(max_length=255, blank=True)
    row_count = models.PositiveIntegerField(default=0)
    imported_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    error_count = models.PositiveIntegerField(default=0)
    errors = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    class Meta:
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"histotico de {self.usuario} modificado en {self.modified_at}"

class Rol(models.Model):
    nombre = models.CharField(
        max_length = 50,
        unique = True,
        verbose_name = "Nombre de Rol"
    )
    descripcion = models.CharField(
        max_length =255,
        verbose_name = "Descripcion del Rol" 
    )

    def __str__(self):
        return self.nombre
    class Meta:
        verbose_name = "Rol"
        verbose_name_plural = "Roles"
        ordering = ['nombre']

class UsuarioHistorico(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE, related_name='historicos')
    
    first_name = models.CharField(max_length=100)
    
    last_name = models.CharField(max_length=100)
    
    edad = models.PositiveIntegerField(null=True, blank=True)
    
    email = models.EmailField(max_length=254)
    
    telefono = models.CharField(max_length=30, blank=True, null=True)
    
    fecha_nacimiento = models.DateField(null=True, blank=True)
    modified_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-modified_at']
        verbose_name = "Histórico de Usuario"
        verbose_name_plural = "Históricos de Usuarios"

    def __str__(self):
        return f"Histórico de {self.usuario} modificado en {self.modified_at}"