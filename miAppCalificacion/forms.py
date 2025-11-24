from django import forms
from .models import CalificacionTributaria, EmpresaSubsidiaria

class CalificacionForm(forms.ModelForm):
    """
    Formulario para el ingreso y edición manual de una Calificación Tributaria.
    """
    class Meta:
        model = CalificacionTributaria
        # Se excluyen los campos de auditoría (usuario_creador, modificador) 
        # porque se llenan automáticamente en la vista (views.py)
        exclude = ('usuario_creador', 'usuario_modificador')
        
        widgets = {
            'fecha_inicio_periodo': forms.DateInput(attrs={'type': 'date'}),
            'fecha_fin_periodo': forms.DateInput(attrs={'type': 'date'}),
        }