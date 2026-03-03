from pymongo import MongoClient
import datetime

# Tu cadena de conexión corregida
uri = "mongodb+srv://admin_comida:Admin123_%24@comidaiguala.toz7ine.mongodb.net/comida_iguala?retryWrites=true&w=majority"

try:
    # Conectar a MongoDB Atlas
    client = MongoClient(uri)
    
    # Verificar conexión
    client.admin.command('ping')
    print("✅ Conexión exitosa a MongoDB Atlas!")
    
    # Obtener la base de datos
    db = client['comida_iguala']
    
    # Probar creación de una colección temporal
    test_collection = db['test_conexion']
    test_collection.insert_one({
        "mensaje": "Prueba de conexión",
        "fecha": datetime.datetime.now(datetime.UTC)
    })
    print("✅ Datos de prueba insertados correctamente")
    
    # Leer los datos
    resultado = test_collection.find_one({"mensaje": "Prueba de conexión"})
    print(f"✅ Datos recuperados: {resultado}")
    
    # Limpiar (opcional)
    test_collection.delete_many({"mensaje": "Prueba de conexión"})
    print("✅ Datos de prueba eliminados")
    
    print("\n🎉 TODO FUNCIONA CORRECTAMENTE! Listo para desplegar.")
    
except Exception as e:
    print(f"❌ Error: {e}")