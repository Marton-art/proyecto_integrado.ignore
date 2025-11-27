from django.db import models
from miAppUsuario.models import Usuario

# Create your models here.
class CalificacionTributaria(models.Model):
    fecha_inicio_periodo = models.DateField()
    fecha_fin_periodo = models.DateField()
    monto_impuesto = models.DecimalField(
        max_digits = 18,
        decimal_places = 2,
        verbose_name = "Monto del Impuesto"
    )
    estado = models.CharField(
        max_length = 20,
        verbose_name = "Estado"
    )
    usuario_creador = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name = 'calificaciones_creadas',
        verbose_name ='Usuario Creador'
    )
    usuario_modificador = models.ForeignKey(
        Usuario,
        on_delete = models.PROTECT,
        related_name = 'calificaciones_modificadas',
        null=True,
        blank=True,
        verbose_name = 'Usuario Modificador'
    )
    empresa_subsidiaria = models.ForeignKey(
        'EmpresaSubsidiaria',
        on_delete = models.CASCADE,
        verbose_name = 'Empresa Subsidiaria'
    )

    class Meta:
        verbose_name = "Calificación Tributaria"
        verbose_name_plural = "Calificaciones Tributarias"
        unique_together = ('empresa_subsidiaria', 'fecha_inicio_periodo')

class EmpresaSubsidiaria(models.Model):
    nombre_legal = models.CharField(max_length=255, unique=True)
    identificacion_fiscal = models.CharField(max_length=50, unique=True)
    actividad_principal = models.CharField(max_length=255)
    regimen_fiscal = models.CharField(max_length=100)
    pais_operacion = models.ForeignKey('Pais', on_delete=models.PROTECT)
    class Meta:
        verbose_name = "Empresa Subsidiaria"
        verbose_name_plural = "Empresas subsidiarias"

    def __str__(self):
        return self.nombre_legal

class Pais(models.Model):
    nombre = models.CharField(
        max_length = 50,
        unique=True,
        verbose_name = "Nombre del País"
    )
    codigo_iso = models.CharField(
        max_length = 3,
        unique = True,
        verbose_name = "Código ISO"
    )
    moneda_local = models.ForeignKey(
        'Moneda',
        on_delete = models.PROTECT,
        verbose_name = "Moneda Local"
    )

    class Meta:
        verbose_name = "País"
        verbose_name_plural = "Países"
    
    def __str__(self):
        return self.nombre

class Moneda(models.Model):
    codigo_iso = models.CharField(
        max_length = 3,
        unique=True,
        verbose_name = "Código ISO"
    )
    nombre = models.CharField(
        max_length = 50,
        unique = True,
        verbose_name = "Nombre de Moneda"
    )
    simbolo = models.CharField(
        max_length = 10,
        verbose_name="Símbolo",
        null=True
    )

    es_moneda_base = models.BooleanField(
        default = False,
        verbose_name = "Moneda Base para Tasa de Cambio"
    )
    class Meta:
        verbose_name = "Moneda"
        verbose_name_plural = "Monedas"
        ordering = ['codigo_iso']
    
    def __str__(self):
        return f"{self.nombre} ({self.codigo_iso})"

class TasaDeCambio(models.Model):
    moneda_origen = models.ForeignKey(
        'Moneda',
        on_delete = models.PROTECT,
        related_name = 'tasas_como_origen',
        verbose_name = "Moneda Origen"
    )
    moneda_destino = models.ForeignKey(
        'Moneda',
        on_delete = models.PROTECT,
        related_name = 'tasas_como_destino',
        verbose_name = "Moneda Destino"
    )
    fecha = models.DateField()
    valor_tasa = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        verbose_name = "Valor de la Tasa"
    )

    class Meta:
        verbose_name = "Tasa de Cambio"
        verbose_name_plural = "Tasas de Cambio"
        unique_together = ('moneda_origen', 'moneda_destino', 'fecha')

    def __str__(self):
        return f"1 {self.moneda_origen.codigo_iso} = {self.valor_tasa} {self.moneda_destino.codigo_iso} ({self.fecha})"