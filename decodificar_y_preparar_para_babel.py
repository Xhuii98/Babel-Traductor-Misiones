import os
import re
import base64
import shutil
import sys

def decode_lgq1_content(content: str) -> str:
    """Reemplaza LGQ1:<base64> por el texto plano decodificado."""
    pattern = r'LGQ1:([A-Za-z0-9+/=]+)'
    
    def replacer(match):
        try:
            decoded = base64.b64decode(match.group(1)).decode('utf-8')
            return decoded
        except Exception:
            return match.group(0)  # Mantiene original si falla
    
    return re.sub(pattern, replacer, content)

def process_modpack(modpack_path: str):
    # Rutas estándar donde Babel busca misiones
    quest_dirs = [
        'kubejs/data/ftbquests/quests',
        'kubejs/data/minecraft/quests',
        'quests',
        'kubejs/data/betterquests/DefaultQuests'
    ]
    
    processed = []
    skipped = []
    
    for rel_dir in quest_dirs:
        full_dir = os.path.join(modpack_path, rel_dir)
        if not os.path.isdir(full_dir):
            continue
            
        for filename in os.listdir(full_dir):
            if not filename.endswith(('.snbt', '.json', '.lang')):
                continue
                
            filepath = os.path.join(full_dir, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    original = f.read()
            except UnicodeDecodeError:
                skipped.append((filepath, "Error de codificación"))
                continue
                
            if 'LGQ1:' not in original:
                skipped.append((filepath, "Sin bloqueos LGQ1"))
                continue
                
            decoded = decode_lgq1_content(original)
            
            # Respaldo automático
            backup_path = filepath + '.backup_lgq1'
            shutil.copy2(filepath, backup_path)
            
            # Sobrescribe en lugar original
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(decoded)
                
            processed.append(filepath)
            print(f"[✓] Decodificado → {filepath}")
            print(f"    Backup: {backup_path}")

    # Resumen
    print("\n" + "="*50)
    if processed:
        print("✅ Archivos listos. Babel los detectará automáticamente al ejecutarse.")
        print("   No necesitas configurar nada extra. Solo corre Babel normalmente.")
    else:
        print("ℹ️ No se encontraron archivos con bloqueos LGQ1 en las rutas estándar.")
        print("   Verifica que el script apunte a la carpeta raíz correcta del modpack.")
        
    if skipped:
        print("\n📄 Archivos ignorados (sin bloqueos o error de lectura):")
        for path, reason in skipped:
            print(f"   - {os.path.basename(path)}: {reason}")
    print("="*50)

if __name__ == '__main__':
    print("🔍 Decodificador LGQ1 → Preparación para Babel")
    print("📂 Arrastra la carpeta RAÍZ del modpack aquí o escribe la ruta:")
    modpack_path = input().strip().strip('"')
    
    if os.path.isdir(modpack_path):
        process_modpack(modpack_path)
    else:
        print("❌ Ruta inválida. Cierra y ejecuta de nuevo.")
        sys.exit(1)
