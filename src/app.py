from flask import Flask, render_template, request, redirect, url_for, jsonify, Response, flash
from pymongo import MongoClient
from bson import json_util
from bson.objectid import ObjectId
import requests
from requests.exceptions import ConnectionError, Timeout, TooManyRedirects
import json
import os
from dotenv import load_dotenv
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from flask_paginate import Pagination, get_page_args

"""Obtener variable de entorno (key)"""
# Obtener el path del directorio actual
BASEDIR = os.path.abspath(os.path.dirname(__file__))
# Conectar el path al .env
load_dotenv(os.path.join(BASEDIR, '.env'))
#Obtenemos la key
SECRET_KEY = os.getenv('SECRET_KEY').encode('utf-8')



"""Funciones de hasheo"""
def get_fenec():
    """Preparar variables para hashear"""
    kdf = PBKDF2HMAC(
    #Implementar método SHA256
    algorithm=hashes.SHA256(),
    length=32,
    salt=b"sAlT"*8,
    iterations=100000,
    backend=default_backend()
    )
    #Obtenemos key de la otra base de datos
    secret_key = mongo_key.key.find()
    secret_key = json_util.dumps(secret_key)  #De bson a string
    secret_key = json.loads(secret_key)       #A json
    secret_key = secret_key[0]['secret_key']  #Get key
    secret_key = json_util.dumps(secret_key)  #Convertir a string
    key = base64.urlsafe_b64encode(kdf.derive(bytes(secret_key, encoding='utf-8'))) #Generar en formato bytes
    return Fernet(key)

def encrypt(data):
    f = get_fenec()
    #Encriptamos y retornamos el token 
    token = f.encrypt(bytes(data, encoding='utf-8'))
    return token.decode()

def decrypt(token):
    f = get_fenec()
    #Desencriptar
    return f.decrypt(bytes(token, encoding='utf-8')).decode()


#Función para cargar datos a la base de datos
def initialize():
    API_KEY = 'd10299d7-d2e5-4638-b552-4485181ba3e1'
    URL = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/listings/latest?start=1&limit=500'
    
    headers = {
    'Accepts': 'application/json',
    'X-CMC_PRO_API_KEY': API_KEY,
    }
  
    try:
        response = requests.get(URL, headers=headers)
        #Lista de criptomonedas
        cryptos = response.json()['data']
        #Lista auxiliar inicial
        l = []
        #Cargar datos a la lista
        for crypto in cryptos:
            #Creación del modelo de datos correspondiente a la criptomoneda
            obj_crypto = {}
            obj_crypto['name'] = crypto['name']
            obj_crypto['symbol'] = crypto['symbol']
            obj_crypto['price'] = str(crypto['quote']['USD']['price'])
            obj_crypto['market_cap'] = str(crypto['quote']['USD']['market_cap'])
            obj_crypto['percent_change_1h'] = str(crypto['quote']['USD']['percent_change_1h'])
            obj_crypto['percent_change_24h'] = str(crypto['quote']['USD']['percent_change_24h'])
            obj_crypto['percent_change_7d'] = str(crypto['quote']['USD']['percent_change_7d'])
            #Pasar objeto a string
            obj_str = json.dumps(obj_crypto)
            l.append(obj_str)
        #Recorrer las lista de objetos y guardarlas en la base de datos
        lista = []
        for crypto in l:
            #Hashear
            token = encrypt(crypto)
            lista.append({'crypto' : token})
        #Guardar en mongo
        mongo.cryptos.insert_many(lista)
    except (ConnectionError, Timeout, TooManyRedirects) as error:
        print(error) 

def get_data():
    #Obtener datos
    cryptos = mongo.cryptos.find()
    #Convertir bson a json
    cryptos1 = json_util.dumps(cryptos)
    #Convertir string a objeto
    cryptos = json.loads(cryptos1)
     #Lista auxiliar
    data = []
    for element in cryptos:
        token = element['crypto']  
        id = element['_id']['$oid']
        #Desencriptar cryptomoneda
        crypto = decrypt(token)
        lista = json.loads(crypto)
        #Le pasamos el id y los valores al objeto cryptomoneda
        data.append({'_id': id, 'crypto': lista})
    return data


# generar tamaño de la lista por paginacion
def set_data(offset=0, per_page=10, data=None):
    return data[offset: offset + per_page]

def generate_pagination(vec):
    #Crear paginacion
    page, per_page, offset = get_page_args(page_parameter='page', per_page_parameter='per_page')
    total = len(vec)
    pagination_data = set_data(offset=offset, per_page=per_page, data=vec)
    pagination = Pagination(page=page, per_page=per_page, total=total, css_framework='bootstrap4')
    return page, per_page, offset, total, pagination_data, pagination

app = Flask(__name__)

"""Session"""
app.secret_key = SECRET_KEY

#Conexión a los host de la base de datos
client = MongoClient(host='db',port=27017)
mongo = client["cryptos"]
client2= MongoClient(host='db2',port=27018)
mongo_key = client['cryptos']


"""Eliminar colecciones"""
#mongo.cryptos.drop()
#mongo_key.key.drop()


"""Cargar criptos"""
collist = mongo_key.list_collection_names()
if "key" not in collist:
    mongo_key.key.insert_one({'secret_key': SECRET_KEY})
#Verificar que exista la coleccion
collist2 = mongo.list_collection_names()
if "cryptos" not in collist2:
    initialize() #De no existir insertamos todos los datos

#Inicializar lista para posterior paginación
data = get_data()

@app.route('/', methods=['GET'])
def get_cryptos():
    if 'search' in request.args:
        #Verificar si se hizo una busqueda
        search = request.args['search']
        list_data = []
        for element in data:
            #Comprobar si cumple con el criterio de busqueda
            if ( search.lower() in element['crypto']['name'].lower() or element['crypto']['name'].lower() == search.lower()) or (element['crypto']['symbol'].lower() == search.lower()):    
                #Le pasamos el id y los valores al objeto cryptomoneda
                list_data.append({'_id': element['_id'], 'crypto': element['crypto'], 'index': data.index(element)})
                continue
        page, per_page, offset, total, pagination_data, pagination = generate_pagination(list_data)
        return render_template('index.html', isSearch=True, search = search,  length=total, data=pagination_data, page=page, per_page=per_page, pagination=pagination)
    else:
        page, per_page, offset, total, pagination_data, pagination = generate_pagination(data)
        return render_template('index.html', isSearch=False, length=total, data=pagination_data, page=page, per_page=per_page, pagination=pagination)
    
@app.route('/info', methods=['GET'])
def getInfo():
    return render_template('info.html')  

@app.route('/search', methods=['GET'])
def search():
     #Obtener parametros de la URL
    search = request.args.get('search')
    return redirect(url_for('get_cryptos', search=search))

@app.route('/top20', methods=['GET'])
def get_top20():
    #Cargar las primeras 20 cryptomonedas dado que ya vienen ordenadas por rank
    list_data = [data[i] for i in range(0,20)]
    length = len(list_data)
    return render_template('top.html', data=list_data, length=length)  

@app.route('/top5', methods=['GET'])
def get_top5():
    #Cargar las primeras 5 cryptomonedas dado que ya vienen ordenadas por rank
    list_data = [data[i] for i in range(0,5)]
    length = len(list_data)
    return render_template('top.html', data=list_data, length=length)  
       
@app.route('/delete/<id>/<index>', methods=['GET'])
def delete_crypto(id, index):
    #Eliminar también de la data del front
    data.pop(int(index))
    try:
        #Eliminar de la base de datos
        mongo.cryptos.delete_one({'_id': ObjectId(id)})
        #Retornar al index
        flash('Cryptocurrency deleted')
        return redirect(url_for('get_cryptos'))
    except (Exception) as e:
        print(e)


#En caso de error de ruta
@app.errorhandler(404)
def not_found(error=None):
    response = jsonify({
        'message': 'Resource Not Found: ' + request.url,
        'status': 404 
    })
    response.status_code = 404
    return response

if __name__ == "__main__":
    app.run(host='src', port='5000', debug=True)