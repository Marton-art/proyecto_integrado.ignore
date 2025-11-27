from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.db import IntegrityError, transaction
from decimal import Decimal
import pandas as pd 
import io
import os
from datetime import date 
from django.http import HttpResponseForbidden, HttpResponse
from miAppUsuario.utils import has_access
from .models import CalificacionTributaria, EmpresaSubsidiaria
from .forms import CalificacionForm
import csv
# Factores del 8 al 37 (total 30 factores)
ALL_FACTORS = [f'Factor {i}' for i in range(8, 38)] 

# Columnas requeridas para la carga de FACTOR (incluyendo el ID Fiscal)
REQUIRED_COLUMNS = [
    'ID_FISCAL_EMPRESA', 'Ejercicio', 'Mercado', 'Instrumento', 'Fecha', 'Secuencia',
    'Numero de dividendo', 'Tipo sociedad', 'Valor Historico', 
] + ALL_FACTORS

# Columnas requeridas para la carga de MONTO (DJ 1948)
REQUIRED_MONTO_COLUMNS = ['ID Fiscal Empresa', 'Fecha Inicio', 'Fecha Fin', 'Monto Impuesto', 'Estado']

# Factores que deben sumar <= 1 (Factores 8 al 19)
FACTORS_TO_SUM = [f'FACTOR {i}' for i in range(8, 20)]

@login_required
def calificaciones_home(request):
    """
    Vista principal o dashboard de la aplicación miAppCalificacion.
    """
    return render(request, 'menu.html')

@login_required
@user_passes_test(lambda user: has_access(user, ['Analista', 'Corredor']), 
                login_url='/forbidden/')
def create_calificacion(request):
    if request.method == "POST":
        form = CalificacionForm(request.POST)
        if form.is_valid():
            calificacion = form.save(commit=False)
            # Lógica de Auditoría: Asignar el usuario que creó el registro
            calificacion.usuario_creador = request.user
            # usuario_modificador se asigna también, ya que es la primera vez que se guarda
            calificacion.usuario_modificador = request.user
            calificacion.save()
            messages.success(request, "Calificación Tributaria creada manualmente con éxito.")
            return redirect('calificaciones:calificacion_list')
        else:
            messages.error(request, "Error en el formulario. Por favor, revise los campos.")
    else:
        form = CalificacionForm()
        
    return render(request, 'create_edit.html', {'form': form})

@login_required
@user_passes_test(lambda user: has_access(user, ['Analista', 'Gerente', 'Corredor']), 
                    login_url='/forbidden/') # Redirige a una vista de acceso denegado
def list_calificaciones(request):
    """Muestra todas las calificaciones, optimizando la consulta a la base de datos."""
    # select_related reduce las consultas al traer la Subsidiaria y el Usuario Creador 
    # en la consulta inicial.
    calificaciones = CalificacionTributaria.objects.select_related(
        'empresa_subsidiaria', 'usuario_creador'
    ).all().order_by('-fecha_inicio_periodo')
    
    context = {
        'calificaciones': calificaciones,
    }
    return render(request, 'list_calificaciones.html', context)

@login_required
@user_passes_test(lambda user: has_access(user, ['Analista', 'Corredor']), 
                             login_url='/forbidden/')
def bulk_upload_factor(request):
    if request.method == 'POST':
        uploaded_file = request.FILES.get('file')

        if not uploaded_file:
            messages.error(request, 'Debe seleccionar un archivo para cargar.')
            return render(request, 'bulk_upload_factor.html')
        
        # Determinación y Lectura del Archivo
        file_ext = os.path.splitext(uploaded_file.name)[1].lower()
        try:
            if file_ext == '.csv':
                # CRÍTICO: Corrección para formato regional (separador coma y decimal coma)
                df = pd.read_csv(
                    io.StringIO(uploaded_file.read().decode('utf-8')), 
                    sep=';', 
                    decimal=','
                )
            elif file_ext in ['.xlsx', '.xls']:
                df = pd.read_excel(uploaded_file)
            else:
                messages.error(request, 'Formato de archivo no soportado. Use CSV o Excel.')
                return render(request, 'bulk_upload_factor.html')
        except Exception as e:
            messages.error(request, f'Error al leer el archivo: {e}')
            return render(request, 'bulk_upload_factor.html')

        # --- inicio de la logica para la validacion y lo que es procesamiento ---
        registros_creados = 0
        registros_actualizados = 0
        errores = [] # Lista para recolectar errores por fila
        
        try:
            # Homologación de columnas
            df.columns = [col.upper().replace(' ', '_') for col in df.columns]
            
            # --- 1. Validación de Columnas ---
            required_cols_normalized = [col.upper().replace(' ', '_') for col in REQUIRED_COLUMNS]
            missing_cols = [col for col in required_cols_normalized if col not in df.columns]

            if missing_cols:
                missing_cols_readable = [col.replace('_', ' ') for col in missing_cols]
                raise ValueError(f"Faltan las siguientes columnas requeridas: {', '.join(missing_cols_readable)}")

            # --- 2. Validación de Regla de Negocio (Suma de Factores 8 al 19 <= 1) ---
            factors_to_sum_upper = [f.upper().replace(' ', '_') for f in FACTORS_TO_SUM]
            # Convertir a numérico (coercing errores a NaN para la suma)
            df[factors_to_sum_upper] = df[factors_to_sum_upper].apply(pd.to_numeric, errors='coerce')
            
            df['SUMA_FACTORES_8_19'] = df[factors_to_sum_upper].sum(axis=1)
            
            validation_errors = df[df['SUMA_FACTORES_8_19'] > 1.00000001]
            
            if not validation_errors.empty:
                error_msg = (
                    f"Validación fallida: {len(validation_errors)} registros tienen una suma de Factores 8 al 19 mayor que 1. "
                    f"Filas con error (muestra): {', '.join([str(i + 2) for i in validation_errors.index.tolist()[:5]])}"
                )
                raise ValueError(error_msg)


            # --- 3. Procesamiento e Inserción/Actualización en Base de Datos ---
            # Se usa transaction.atomic() por fila para asegurar la unicidad y reversión del fallo
            
            for index, row in df.iterrows():
                id_fiscal = None # Inicializar para asegurar que esté disponible en el except
                
                try:
                    # **SOLUCIÓN CRÍTICA** Búsqueda de la Subsidiaria por identificacion_fiscal (no por PK)
                    id_fiscal = str(row['ID_FISCAL_EMPRESA']).split('.')[0].strip()
                    subsidiaria_obj = EmpresaSubsidiaria.objects.get(identificacion_fiscal=id_fiscal)

                    # --- Definición de Clave Única y Datos ---
                    unique_key = {
                        'empresa_subsidiaria': subsidiaria_obj, 
                        'ejercicio': int(row['EJERCICIO']),
                        'instrumento': row['INSTRUMENTO'],
                        'fecha_pago': pd.to_datetime(row['FECHA']).date(), 
                        'secuencia': int(row['SECUENCIA']),
                        'numero_dividendo': int(row['NUMERO_DE_DIVIDENDO']), # Campo agregado
                    }
                    
                    update_data = {
                        'mercado': row['MERCADO'],
                        'tipo_sociedad': row['TIPO_SOCIEDAD'],
                        'valor_historico': Decimal(str(row['VALOR_HISTORICO'])),
                        'origen': 'Carga Masiva Factor', 
                        'usuario_modificador': request.user,
                    }
                    
                    # Mapear los 30 factores (8 al 37) de forma dinámica
                    for factor_num in range(8, 38):
                        col_name = f'FACTOR_{factor_num}'
                        model_field_name = f'factor_{factor_num}'
                        factor_value = row.get(col_name)
                        
                        update_data[model_field_name] = Decimal(str(factor_value)) if pd.notna(factor_value) else None

                    
                    # bloque transaccional por fila
                    with transaction.atomic():
                        # Uso de update_or_create con trazabilidad
                        existing_calificacion = CalificacionTributaria.objects.filter(**unique_key).only('usuario_creador').first()
                        
                        calificacion, created = CalificacionTributaria.objects.update_or_create(
                            **unique_key,
                            defaults={
                                **update_data,
                                'usuario_creador': request.user if created or not existing_calificacion else existing_calificacion.usuario_creador
                            }
                        )
                        
                        if created:
                            registros_creados += 1
                        else:
                            registros_actualizados += 1
                            
                # Manejo de errores por fila
                except EmpresaSubsidiaria.DoesNotExist:
                    errores.append(f"Fila {index + 2}: El ID Fiscal '{id_fiscal}' de la empresa no existe.")
                    continue
                except (ValueError, TypeError) as ve:
                    # Captura errores de conversión (Decimal, Int, Fecha)
                    errores.append(f"Fila {index + 2}: Error de formato de dato (Ej. Fecha, Número). Detalle: {str(ve).splitlines()[0]}")
                    continue
                except Exception as e:
                    errores.append(f"Fila {index + 2}: Error desconocido: {str(e).splitlines()[0]}")
                    continue


            # --- 4. Mensaje de Éxito y Errores Finales ---
            
            if errores:
                # Mostrar todos los errores recolectados
                error_summary = ' | '.join(errores)  
                messages.warning(
                    request, 
                    f'Carga finalizada con {len(errores)} errores. Revise los detalles: {error_summary}'
                )

            messages.success(
                request, 
                f'El archivo "{uploaded_file.name}" fue procesado. {registros_creados} creados, {registros_actualizados} actualizados.'
            )
            
            return redirect('calificaciones:calificacion_list')
            
        # --- Manejo de Errores de Pre-Procesamiento (Columnas/Suma) ---
        except ValueError as e:
            messages.error(request, f'Error de validación de datos: {e}')
            return render(request, 'bulk_upload_factor.html')
            
        except Exception as e:
            messages.error(request, f'Error interno al procesar el archivo: {e}')
            return render(request, 'bulk_upload_factor.html')

    return render(request, 'bulk_upload_factor.html')

@login_required 
# Usa el decorador de acceso que ya tienes (Analista/Corredor o el que corresponda)
@user_passes_test(lambda user: has_access(user, ['Analista', 'Corredor']), 
                 login_url='/forbidden/')
# miAppCalificacion/views.py

def descargar_plantilla_factores_view(request):
    """Genera y sirve el archivo CSV con los encabezados requeridos para Factores."""
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="Plantilla_Carga_Masiva_Factores.csv"' 

    writer = csv.writer(response) 
    
    # Metadatos requeridos (9 campos) - Usamos mayúsculas según el error
    metadata_headers = [
        # Asumimos que estos 6 campos SÍ fueron encontrados por el validador
        'ID_FISCAL_EMPRESA', 'EJERCICIO', 'MERCADO', 'INSTRUMENTO', 
        'FECHA', 'SECUENCIA', 
        # Los campos que se reportan como faltantes
        'NUMERO DE DIVIDENDO', 'TIPO SOCIEDAD', 'VALOR HISTORICO', 
    ]
    
    # 30 Factores (del Factor 8 al Factor 37)
    # CORRECCIÓN: Usamos .upper() para generar FACTOR 8, FACTOR 9, etc.
    factor_headers = [f'FACTOR {i}' for i in range(8, 38)] 
    
    # Escribe todos los encabezados
    writer.writerow(metadata_headers + factor_headers)
    
    # --- fila de Ejemplo (El cuerpo de la fila de ejemplo está bien) ---
    
    # Valores de metadatos (9 valores)
    example_row = [
        '76000000-1', '2025', 'CHILE', 'ACCION', '2025-01-01', '1', 
        '0', 'SA', '1000.00', 
    ]
    
    # Valores de factores (30 valores)
    factors_to_sum_count = 12
    valor_unitario = 1.00 / factors_to_sum_count 
    
    for i in range(8, 38): 
        if i <= 19:
            example_row.append(f'{valor_unitario:.5f}')
        else:
            example_row.append('0.00000') 
            
    writer.writerow(example_row)
    
    return response


@login_required
@user_passes_test(lambda user: has_access(user, ['Analista', 'Corredor']), 
                  login_url='/forbidden/')
def bulk_upload_monto(request):
    """
    Implementa la Carga Masiva (RF 03) y la lógica de Actualización (HDU 10)
    basada en la llave única (Subsidiaria + Fecha de Inicio).
    """
    if request.method == "POST":
        if 'file' in request.FILES:
            file = request.FILES['file']
            
            if not file.name.endswith(('.csv', '.xlsx', '.xls')):
                messages.error(request, 'El archivo debe ser CSV o Excel.')
                return redirect('calificaciones:bulk_upload_monto')

            try:
                # Lectura con Pandas: CORRECCIÓN DE FORMATO REGIONAL
                if file.name.endswith('.csv'):
                    # CRÍTICO: Usamos sep=';' (punto y coma) y decimal=',' (coma decimal)
                    # La línea se divide en dos para cumplir con PEP 8
                    df = pd.read_csv(
                        io.StringIO(file.read().decode('utf-8')), 
                        sep=';', 
                        decimal=','
                    ) 
                else:
                    df = pd.read_excel(file)
                
                df = df.fillna('')
                
                # Homologación de columnas
                df.columns = [col.upper().replace(' ', '_') for col in df.columns]
                
                required_cols_normalized = [
                    col.upper().replace(' ', '_') for col in REQUIRED_MONTO_COLUMNS
                ]
                
                if not all(col in df.columns for col in required_cols_normalized):
                    missing_cols_readable = [
                        col for col in REQUIRED_MONTO_COLUMNS 
                        if col.upper().replace(' ', '_') not in df.columns
                    ]
                    messages.error(
                        request, 
                        f'El archivo debe contener las siguientes columnas requeridas: {", ".join(missing_cols_readable)}'
                    )
                    return redirect('calificaciones:bulk_upload_monto')
                
                creados = 0
                actualizados = 0
                errores = []
                
                with transaction.atomic():
                    for index, row in df.iterrows():
                        try:
                            # Obtener y limpiar ID Fiscal (Maneja el caso de que Pandas lo lea como float)
                            id_fiscal = str(row['ID_FISCAL_EMPRESA']).split('.')[0].strip()
                            subsidiaria_obj = EmpresaSubsidiaria.objects.get(
                                identificacion_fiscal=id_fiscal
                            )
                            
                            # Conversión de fechas y montos
                            fecha_inicio = pd.to_datetime(row['FECHA_INICIO']).date()
                            fecha_fin = pd.to_datetime(row['FECHA_FIN']).date()
                            monto_impuesto = Decimal(str(row['MONTO_IMPUESTO']))
                            
                            key_fields = {
                                'empresa_subsidiaria': subsidiaria_obj,
                                'fecha_inicio_periodo': fecha_inicio
                            }
                            
                            update_defaults = {
                                'fecha_fin_periodo': fecha_fin,
                                'monto_impuesto': monto_impuesto,
                                'estado': str(row['ESTADO']),
                                'origen': 'Carga Masiva Monto',
                                'usuario_modificador': request.user 
                            }
                            
                            existing_calificacion = CalificacionTributaria.objects.filter(
                                **key_fields
                            ).only('usuario_creador').first()

                            calificacion, created = CalificacionTributaria.objects.update_or_create(
                                **key_fields,
                                defaults={
                                    **update_defaults,
                                    'usuario_creador': request.user if created or not existing_calificacion else existing_calificacion.usuario_creador
                                }
                            )

                            if created:
                                creados += 1
                            else:
                                actualizados += 1
                                
                        except EmpresaSubsidiaria.DoesNotExist:
                            errores.append(
                                f"Fila {index + 2}: El ID Fiscal {id_fiscal} de la empresa no existe."
                            )
                        except (ValueError, TypeError) as e:
                            # Este es el bloque que buscamos solucionar (Monto/Fecha)
                            errores.append(
                                f"Fila {index + 2}: Error en formato (Fecha/Monto). Detalle: {e}"
                            )
                        except IntegrityError:
                            errores.append(
                                f"Fila {index + 2}: Error de integridad de datos (posiblemente fechas inválidas)."
                            )
                        except Exception as e:
                            errores.append(f"Fila {index + 2}: Error desconocido: {e}")

                messages.success(
                    request, 
                    f'Carga masiva finalizada: {creados} creados, {actualizados} actualizados.'
                )
                if errores:
                    error_summary = ' | '.join(errores[:5]) + ('...' if len(errores) > 5 else '')
                    messages.warning(
                        request, 
                        f'Se encontraron {len(errores)} errores. Revise los detalles: {error_summary}'
                    )
                
                return redirect('calificaciones:calificacion_list')
            
            except Exception as e:
                messages.error(
                    request, 
                    f'Error fatal al procesar el archivo: {e}'
                )
                return redirect('calificaciones:bulk_upload_monto')
            
    return render(request, 'bulk_upload_monto.html')

@login_required 
@user_passes_test(lambda user: has_access(user, ['Analista', 'Corredor']), 
                 login_url='/forbidden/')
def descargar_plantilla_montos_view(request):
    # Configurar la respuesta HTTP
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="Plantilla_Montos_Tributarios.csv"' 

    # Esta línea es correcta y necesaria
    writer = csv.writer(response) 
    
    # Definir los encabezados (¡DEBEN COINCIDIR EXACTAMENTE!)
    headers = ['ID Fiscal Empresa', 'Fecha Inicio', 'Fecha Fin', 'Monto Impuesto', 'Estado']
    
    writer.writerow(headers)
    
    # Fila de ejemplo
    writer.writerow(['76000000-1', '2025-01-01', '2025-03-31', '5500000.00', 'Vigente'])
    
    return response


# --- edicion de calificacion ---

@login_required
@user_passes_test(lambda user: has_access(user, ['Analista', 'Gerente', 'Corredor']), 
                login_url='/forbidden/')
def edit_calificacion(request, pk):
    calificacion = get_object_or_404(CalificacionTributaria, pk=pk)

    if request.method == "POST":
        form = CalificacionForm(request.POST, instance=calificacion)
        
        if form.is_valid():
            calificacion_instance = form.save(commit=False)
            # Lógica de Auditoría: Asignar el usuario que modificó
            calificacion_instance.usuario_modificador = request.user
            calificacion_instance.save()
            messages.success(request, 'Calificación actualizada exitosamente.') 
            return redirect('calificaciones:calificacion_list')
        else:
            messages.error(request, 'Error al actualizar. Revise los campos.')
    else:
        form = CalificacionForm(instance=calificacion)
    
    return render(request, 'create_edit.html', {'form': form, 'calificacion': calificacion})

# --- eliminacion de calificacion ---
@login_required
@user_passes_test(lambda user: has_access(user, []), 
                login_url='/forbidden/')
def delete_calificacion(request, pk):
    calificacion = get_object_or_404(CalificacionTributaria, pk=pk)
    
    if request.method == "POST":
        try:
            calificacion.delete()
            messages.success(request, f'Calificación eliminada para {calificacion.empresa_subsidiaria.nombre_legal}.')
        except Exception as e:
            messages.error(request, f'Error al eliminar la calificación: {e}')
        return redirect('calificaciones:calificacion_list')
    
    return render(request, 'delete_confirm.html', {'calificacion': calificacion})

def forbidden_access(request):
    return HttpResponseForbidden("<h1>Acceso Denegado</h1><p>No tienes los permisos necesarios para acceder a esta sección.</p>")