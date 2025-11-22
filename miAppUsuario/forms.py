# miAppUsuario/forms.py (UPDATED)
from django import forms
from .models import Usuario 

class UsuarioForm(forms.ModelForm):
    contraseña = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Mínimo 8 caracteres'}), 
        label='Contraseña',
        help_text='Mínimo 8 caracteres.'
    )
    contraseña2 = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Repita la contraseña'}), 
        label='Confirmar Contraseña'
    )

    class Meta:
        model = Usuario
        fields = ['first_name', 'last_name', 'email', 'telefono', 'edad', 'rol_usuario', 'pais_usuario', 'is_active'] 
        
        # Opcional: Mejora la experiencia de usuario con placeholders
        widgets = {
            'nombre': forms.TextInput(attrs={'placeholder': 'Ingrese su nombre'}),
            'apellido': forms.TextInput(attrs={'placeholder': 'Ingrese su apellido'}),
            'email': forms.EmailInput(attrs={'placeholder': 'ejemplo@correo.com'}),
            'telefono': forms.TextInput(attrs={'placeholder': 'Ej: +56912345678 (opcional)'}),
            'edad': forms.NumberInput(attrs={'placeholder': 'Su edad (opcional)'}),
            # Los campos Foreign Key (rol_usuario, pais_usuario) se renderizan automáticamente como <select>
        }

    # Lógica de validación para contraseñas (la dejamos igual)
    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("contraseña")
        password2 = cleaned_data.get("contraseña2")

        if password and password2 and password != password2:
            raise forms.ValidationError(
                "Las contraseñas ingresadas no coinciden."
            )
        
        return cleaned_data
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # 🔑 Lógica CRUCIAL para la edición
        # Si el formulario está ligado a una instancia existente (self.instance tiene un PK),
        # significa que estamos EDITANDO. Hacemos la contraseña opcional.
        if self.instance and self.instance.pk:
            self.fields['contraseña'].required = False
            self.fields['contraseña2'].required = False
            
        # Opcional: Para añadir el estilo 'form-control' a todos los campos
        for field_name, field in self.fields.items():
            if field_name not in ['is_active']:
                # Aquí se ignoran los placeholders definidos en widgets si se ponen atributos fijos
                # Si quieres que se mantengan los placeholders definidos en 'widgets', 
                # puedes ser más selectivo aquí.
                field.widget.attrs.update({'class': 'form-control'})