from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import IntegrityError, transaction
from decimal import Decimal
import pandas as pd 
import io
import os
from datetime import date # Importar date para manejar fechas
from django.db.models import F # Se recomienda importar F para filtros complejos si se requiriera, pero no es estrictamente necesario aquí.

from .models import CalificacionTributaria, EmpresaSubsidiaria
from .forms import CalificacionForm

# --- CONSTANTES GLOBALES ---
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
FACTORS_TO_SUM = [f'Factor {i}' for i in range(8, 20)]

@login_required
def calificaciones_home(request):
    """
    Vista principal o dashboard de la aplicación miAppCalificacion.
    """
    # Usamos 'calificacion/home.html' para evitar colisión de nombres
    # con cualquier otro 'home.html' de otras apps.
    return render(request, 'menu.html')

# --- VISTA 1: CREAR CALIFICACIÓN (CRUD C) ---
@login_required(login_url='login')
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
            return redirect('calificaciones:list')
        else:
            messages.error(request, "Error en el formulario. Por favor, revise los campos.")
    else:
        form = CalificacionForm()
        
    return render(request, 'create_edit.html', {'form': form})

# --- VISTA 2: LISTAR CALIFICACIONES (CRUD R) ---
@login_required(login_url='login')
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


# --- VISTA 3: CARGA MASIVA (FACTOR) ---
@login_required(login_url='login')
def bulk_upload_factor(request):
    if request.method == 'POST':
        uploaded_file = request.FILES.get('file')

        if not uploaded_file:
            messages.error(request, 'Debe seleccionar un archivo para cargar.')
            return render(request, 'calificacion/bulk_upload_factor.html')
        
        # 1. Determinación y Lectura del Archivo
        file_ext = os.path.splitext(uploaded_file.name)[1].lower()
        try:
            if file_ext == '.csv':
                df = pd.read_csv(io.StringIO(uploaded_file.read().decode('utf-8')))
            elif file_ext in ['.xlsx', '.xls']:
                # Importante: para .xls y .xlsx Pandas requiere el archivo en sí, no el stream decodificado.
                df = pd.read_excel(uploaded_file)
            else:
                messages.error(request, 'Formato de archivo no soportado. Use CSV o Excel.')
                return render(request, 'calificacion/bulk_upload_factor.html')
        except Exception as e:
            messages.error(request, f'Error al leer el archivo: {e}')
            return render(request, 'calificacion/bulk_upload_factor.html')


        # --- INICIO LÓGICA DE VALIDACIÓN Y PROCESAMIENTO ---
        num_registros = 0
        try:
            # Homologación de columnas (Uppercase y sin espacios para fácil acceso)
            df.columns = [col.upper().replace(' ', '_') for col in df.columns]
            
            # 2. **CORRECCIÓN:** Validación de Columnas contra la lista normalizada
            required_cols_normalized = [col.upper().replace(' ', '_') for col in REQUIRED_COLUMNS]
            missing_cols = [col for col in required_cols_normalized if col not in df.columns]

            if missing_cols:
                # Revertir a formato legible para el mensaje de error
                missing_cols_readable = [col.replace('_', ' ') for col in missing_cols]
                raise ValueError(f"Faltan las siguientes columnas requeridas: {', '.join(missing_cols_readable)}")

            # 3. Validación de la Regla de Negocio (Suma de Factores 8 al 19 <= 1)
            # Asegurar que los factores son numéricos y luego calcular la suma
            factors_to_sum_upper = [f.upper().replace(' ', '_') for f in FACTORS_TO_SUM]
            # Usar errors='coerce' reemplaza los valores no numéricos con NaN
            df[factors_to_sum_upper] = df[factors_to_sum_upper].apply(pd.to_numeric, errors='coerce')
            
            # Crear una columna con la suma total para la validación
            df['SUMA_FACTORES_8_19'] = df[factors_to_sum_upper].sum(axis=1)
            
            # Identificar filas que violan la regla (Suma > 1)
            validation_errors = df[df['SUMA_FACTORES_8_19'] > 1.00000001]
            
            if not validation_errors.empty:
                error_msg = f"Validación fallida: {len(validation_errors)} registros tienen una suma de Factores 8 al 19 mayor que 1."
                raise ValueError(error_msg)


            # 4. Procesamiento e Inserción/Actualización en Base de Datos (Transacción)
            with transaction.atomic():
                for index, row in df.iterrows():
                    
                    try:
                        # 4.1 Búsqueda de la Subsidiaria por ID Fiscal
                        id_fiscal = str(row['ID_FISCAL_EMPRESA']).strip()
                        subsidiaria_obj = EmpresaSubsidiaria.objects.get(identificacion_fiscal=id_fiscal)

                        # 4.2 Definición de la clave única
                        unique_key = {
                            'empresa_subsidiaria': subsidiaria_obj, 
                            'ejercicio': int(row['EJERCICIO']),
                            'instrumento': row['INSTRUMENTO'],
                            # Convertir la fecha a objeto date
                            'fecha_pago': pd.to_datetime(row['FECHA']).date(), 
                            'secuencia': int(row['SECUENCIA']),
                        }
                        
                        # 4.3 Datos a actualizar/crear
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
                            
                            # Convertir a Decimal, manejar nulos
                            update_data[model_field_name] = Decimal(str(factor_value)) if pd.notna(factor_value) else None

                        # 4.4 Uso de update_or_create con trazabilidad
                        # Buscar si ya existe para preservar el usuario_creador
                        existing_calificacion = CalificacionTributaria.objects.filter(**unique_key).only('usuario_creador').first()
                        
                        calificacion, created = CalificacionTributaria.objects.update_or_create(
                            **unique_key,
                            defaults={
                                **update_data,
                                # Asignar creador si es nuevo, mantener si es actualización.
                                'usuario_creador': request.user if created or not existing_calificacion else existing_calificacion.usuario_creador
                            }
                        )
                        num_registros += 1
                        
                    except EmpresaSubsidiaria.DoesNotExist:
                        # Se lanza una excepción específica para ser capturada fuera del atomic block
                        raise EmpresaSubsidiaria.DoesNotExist(f"Fila {index + 2}: El ID Fiscal {id_fiscal} de la empresa no existe. El registro no fue creado/actualizado.")
                    except (ValueError, TypeError) as ve:
                        # Capturar errores de conversión de datos (Fecha, Decimal, Int)
                        raise ValueError(f"Fila {index + 2}: Error de formato de dato (Fecha, Número o ID Fiscal). Detalle: {ve}. El registro no fue creado/actualizado.")
                    except Exception as e:
                        # Captura cualquier otro error de registro
                        raise Exception(f"Fila {index + 2}: Error desconocido en el procesamiento del registro: {e}. El registro no fue creado/actualizado.")


            # 5. Mensaje de Éxito
            messages.success(request, f'El archivo "{uploaded_file.name}" fue cargado y {num_registros} factores fueron procesados con éxito.')
            
            return redirect('calificaciones:list')
            
        except EmpresaSubsidiaria.DoesNotExist as e:
            messages.error(request, f'Error al procesar el archivo: {e}')
            return render(request, 'bulk_upload_factor.html')
            
        except ValueError as e:
            # Captura errores de validación (columnas, suma de factores, formato de datos)
            messages.error(request, f'Error de validación de datos: {e}')
            return render(request, 'bulk_upload_factor.html')
            
        except Exception as e:
            # Captura errores generales (DB, lógica no controlada)
            messages.error(request, f'Error interno al procesar el archivo: {e}')
            return render(request, 'bulk_upload_factor.html')

    return render(request, 'bulk_upload_factor.html')

# --- VISTA 4: CARGA MASIVA (MONTO) ---

@login_required(login_url='login')
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
                # Lectura simple con Pandas
                if file.name.endswith('.csv'):
                    df = pd.read_csv(io.StringIO(file.read().decode('utf-8')))
                else:
                    df = pd.read_excel(file)
                
                df = df.fillna('')
                
                # Homologación de columnas
                df.columns = [col.upper().replace(' ', '_') for col in df.columns]
                
                # **CORRECCIÓN:** Validación de Columnas con la constante global
                required_cols_normalized = [col.upper().replace(' ', '_') for col in REQUIRED_MONTO_COLUMNS]
                if not all(col in df.columns for col in required_cols_normalized):
                    # Revertir a formato legible para el mensaje de error
                    missing_cols_readable = [col for col in REQUIRED_MONTO_COLUMNS if col.upper().replace(' ', '_') not in df.columns]
                    messages.error(request, f'El archivo debe contener las siguientes columnas requeridas: {", ".join(missing_cols_readable)}')
                    return redirect('calificaciones:bulk_upload_monto')
                
                creados = 0
                actualizados = 0
                errores = []
                
                # Transacción Atómica: Si hay un error, se revierte todo.
                with transaction.atomic():
                    for index, row in df.iterrows():
                        try:
                            # 1. Búsqueda de la Subsidiaria por ID Fiscal (Clave de la Lógica)
                            id_fiscal = str(row['ID_FISCAL_EMPRESA']).strip()
                            subsidiaria_obj = EmpresaSubsidiaria.objects.get(identificacion_fiscal=id_fiscal)
                            
                            # Conversión de fechas y montos
                            fecha_inicio = pd.to_datetime(row['FECHA_INICIO']).date()
                            fecha_fin = pd.to_datetime(row['FECHA_FIN']).date()
                            monto_impuesto = Decimal(str(row['MONTO_IMPUESTO']))
                            
                            # 2. Llave Única para actualizar o crear
                            key_fields = {
                                'empresa_subsidiaria': subsidiaria_obj,
                                'fecha_inicio_periodo': fecha_inicio
                            }
                            
                            # 3. Datos a insertar/actualizar
                            update_defaults = {
                                'fecha_fin_periodo': fecha_fin,
                                'monto_impuesto': monto_impuesto,
                                'estado': str(row['ESTADO']),
                                'origen': 'Carga Masiva Monto',
                                'usuario_modificador': request.user # Trazabilidad
                            }
                            
                            # **CORRECCIÓN:** Uso de update_or_create con trazabilidad eficiente
                            # Paso 1: Buscar si ya existe para preservar el usuario_creador
                            existing_calificacion = CalificacionTributaria.objects.filter(**key_fields).only('usuario_creador').first()

                            # Paso 2: Crear o Actualizar
                            calificacion, created = CalificacionTributaria.objects.update_or_create(
                                **key_fields,
                                defaults={
                                    **update_defaults,
                                    # Si es nuevo, asigna el creador (request.user). 
                                    # Si es actualización, mantiene el creador original.
                                    'usuario_creador': request.user if created or not existing_calificacion else existing_calificacion.usuario_creador
                                }
                            )

                            if created:
                                creados += 1
                            else:
                                actualizados += 1
                                
                        except EmpresaSubsidiaria.DoesNotExist:
                            errores.append(f"Fila {index + 2}: El ID Fiscal {id_fiscal} de la empresa no existe.")
                        except (ValueError, TypeError):
                            errores.append(f"Fila {index + 2}: Error en formato de Fecha ({row['FECHA_INICIO']}/{row['FECHA_FIN']}) o Monto ({row['MONTO_IMPUESTO']}).")
                        except IntegrityError:
                            errores.append(f"Fila {index + 2}: Error de integridad de datos (posiblemente fechas inválidas).")
                        except Exception as e:
                            errores.append(f"Fila {index + 2}: Error desconocido: {e}")

                messages.success(request, f'Carga masiva finalizada: {creados} creados, {actualizados} actualizados.')
                if errores:
                    # Mostrar errores como un mensaje de warning o un mensaje de error si el usuario no puede descargar el detalle.
                    messages.warning(request, f'Se encontraron {len(errores)} errores. Revise los detalles.')
                
                return redirect('calificaciones:list')
            
            except Exception as e:
                # Captura errores generales antes de entrar al bucle (ej. error al leer el archivo o error de columna)
                messages.error(request, f'Error fatal al procesar el archivo: {e}')
                return redirect('calificaciones:bulk_upload_monto')
            
    return render(request, 'bulk_upload_monto.html')

# --- VISTA 5: EDITAR CALIFICACIÓN (CRUD U) ---

@login_required(login_url='login')
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
            return redirect('calificaciones:list')
        else:
            messages.error(request, 'Error al actualizar. Revise los campos.')
    else:
        form = CalificacionForm(instance=calificacion)
    
    return render(request, 'create_edit.html', {'form': form, 'calificacion': calificacion})

# --- VISTA 6: ELIMINAR CALIFICACIÓN (CRUD D) ---

@login_required(login_url='login')
def delete_calificacion(request, pk):
    calificacion = get_object_or_404(CalificacionTributaria, pk=pk)
    
    if request.method == "POST":
        try:
            calificacion.delete()
            messages.success(request, f'Calificación eliminada para {calificacion.empresa_subsidiaria.nombre_legal}.')
        except Exception as e:
            messages.error(request, f'Error al eliminar la calificación: {e}')
        return redirect('calificaciones:list')
    
    return render(request, 'delete_confirm.html', {'calificacion': calificacion})