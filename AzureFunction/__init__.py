import datetime
import logging
import requests
import json
# update pass in getPass() 
from . import privatepass
from arcgis.gis import GIS
from  arcgis.features  import Feature
from  arcgis.geometry  import Point


import azure.functions as func

idArr = []
measuresDict = {}
measuresDict["values"] = []

def parseData(resultJson):
    # get the body
    body = resultJson['body']
    # for each item flatten the value
    for item in body:
        
        measureFlat = {}
        measureFlat["_id"] = item["_id"]
        # check that the value is unique if multiple request send back the same infos
        if(measureFlat["_id"] in idArr ):
            continue
        else:
            idArr.append(measureFlat["_id"])

        measureFlat["X"] = item["place"]["location"][0]
        measureFlat["Y"] = item["place"]["location"][1]
        measureFlat["altitude"] = item["place"]["altitude"]
        #default value empty
        measureFlat["temperature"] = ""
        measureFlat["humidity"] =""
        measureFlat["pressure"] =""
        #rain
        measureFlat["rain_60min"] =""
        measureFlat["rain_24h"] =""
        measureFlat["rain_live"] = ""
        measureFlat["rain_timeutc"] = ""
        #wind
        measureFlat["wind_strength"] =""
        measureFlat["wind_angle"] =""
        measureFlat["gust_strength"] = ""
        measureFlat["gust_angle"] = ""
        measureFlat["wind_timeutc"] = ""
        
        
        
        
        # set values
        for key,val in item["measures"].items():
            if "type" in val:
                #pression or temp/hum
                if val["type"] == ['temperature', 'humidity']:
                    measureFlat["temperature"] = next(iter(val["res"].values()))[0]
                    measureFlat["humidity"] = next(iter(val["res"].values()))[1]
                if val["type"] == ['pressure']:
                    measureFlat["pressure"] = next(iter(val["res"].values()))[0]
            #if rain
            if "rain_60min" in val:
                measureFlat["rain_60min"] = val["rain_60min"]
                measureFlat["rain_24h"] = val["rain_24h"]
                measureFlat["rain_live"] = val["rain_live"]
                measureFlat["rain_timeutc"] = val["rain_timeutc"]
            #if wind
            if "wind_strength" in val:
                measureFlat["wind_strength"] = val["wind_strength"]
                measureFlat["wind_angle"] =val["wind_angle"]
                measureFlat["gust_strength"] = val["gust_strength"]
                measureFlat["gust_angle"] = val["gust_angle"]
                measureFlat["wind_timeutc"] = val["wind_timeutc"]
        measuresDict["values"].append(measureFlat)







def main(mytimer: func.TimerRequest) -> None:
    utc_timestamp = datetime.datetime.utcnow().replace(
        tzinfo=datetime.timezone.utc).isoformat()

    if mytimer.past_due:
        logging.info('The timer is past due!')


    
    

    # function parse the data from netatmo and share the infos in measuresDict
    # First we need to authenticate, give back an access_token used by requests 
    payload = {'grant_type': 'refresh_token',
            'client_id': privatepass.getClientId(),
            'client_secret': privatepass.getClientSecret(),
            'refresh_token' : privatepass.getRefreshToken(),
            'scope': 'read_station'}
    try:
        response = requests.post("https://api.netatmo.com/oauth2/token", data=payload)
        response.raise_for_status()
        access_token=response.json()["access_token"]
        refresh_token=response.json()["refresh_token"]
        scope=response.json()["scope"]
        
    except requests.exceptions.HTTPError as error:
        print(error.response.status_code, error.response.text)



    '''
    netatmo data is dependent on extent queried, the more you zoom the more you

    https://dev.netatmo.com/en-US/resources/technical/guides/ratelimits
    Per user limits
    50 requests every 10 seconds
    > One global request, and multiple litle on a specific area, while staying under api limit
    '''

    # first global request

    payload = {'access_token': access_token,
            'lat_ne':52.677040100097656,
            'lon_ne': 13.662185668945312,
            'lat_sw' : 52.374916076660156,
            'lon_sw':13.194580078125
                # filter wierd/wrong data 
                ,'filter': 'true'
            }
    try:
        response = requests.post("https://api.netatmo.com/api/getpublicdata", data=payload)
        response.raise_for_status()
        resultJson=response.json()
        parseData(resultJson)
        
    except requests.exceptions.HTTPError as error:
        print(error.response.status_code, error.response.text)



    base_lat_ne = 52.677040100097656
    base_lon_ne = 13.662185668945312
    base_lat_sw = 52.374916076660156
    base_lon_sw = 13.194580078125


    # calc each subextent size
    lon_step = (base_lon_ne - base_lon_sw)/4
    lat_step = (base_lat_ne - base_lat_sw)/4

    currentStep=0

    # we cut the extent in x/x and go through each sub-extent
    lat_sw = base_lat_sw
    while(lat_sw < base_lat_ne):
        lat_ne = lat_sw + lat_step
        #reset the lon_sw
        lon_sw = base_lon_sw
        while(lon_sw < base_lon_ne):
            lon_ne = lon_sw + lon_step
            payload = {'access_token': access_token,
                'lat_sw' : lat_sw,
                'lon_sw':lon_sw,
                'lat_ne':lat_ne,
                'lon_ne': lon_ne,
                    # filter wierd/wrong data 
                    'filter': 'true'
                }
            try:
                currentStep=currentStep+1
                #print(str(lat_ne)  + "   " + str(lon_ne))
                response = requests.post("https://api.netatmo.com/api/getpublicdata", data=payload)
                response.raise_for_status()
                resultJson=response.json()
                # parse the data
                parseData(resultJson)
            except requests.exceptions.HTTPError as error:
                print(error.response.status_code, error.response.text)
            lon_sw = lon_ne
        lat_sw = lat_ne



    # last part - json can be dumped in a file for test purpose or geoevent server integration
    #with open('dataNetAtmo.json', 'w') as outfile:  
    #    json.dump(measuresDict, outfile)

    # or we can get each object and push it as a feature !

    # connect to to the gis
    # get the feature layer
    gis = GIS("https://esrich.maps.arcgis.com", "cede_esrich", privatepass.getPass())       
    netAtmoFl =  gis.content.get('0078c29282174460b57ce7ca72262549').layers[0]        

    featuresToAdd = []
    '''" sample value
            _id": "70:ee:50:3f:4d:26",
            "X": 13.5000311,
            "Y": 52.5020974,
            "altitude": 37,
            "temperature": 10.4,
            "humidity": 71,
            "pressure": 1018.1,
            "rain_60min": "",
            "rain_24h": "",
            "rain_live": "",
            "rain_timeutc": "",
            "wind_strength": "",
            "wind_angle": "",
            "gust_strength": "",
            "gust_angle": "",
            "wind_timeutc": ""
            '''

    for measure in measuresDict["values"]:
        attr = dict()
        attr["id"] = measure["_id"]
        attr["altitude"] = measure["altitude"]
        attr["temperature"] = measure["temperature"]
        attr["humidity"] = measure["humidity"]
        attr["pressure"] = measure["pressure"]
        attr["rain_60min"] = measure["rain_60min"]
        attr["rain_24h"] = measure["rain_24h"]
        attr["rain_live"] = measure["rain_live"]
        attr["rain_timeutc"] = measure["rain_timeutc"]
        attr["wind_strength"] = measure["wind_strength"]
        attr["wind_angle"] = measure["wind_angle"]
        attr["gust_strength"] = measure["gust_strength"]
        attr["gust_angle"] = measure["gust_angle"]
        attr["wind_timeutc"] = measure["wind_timeutc"]
        lat = measure["Y"]
        lon = measure["X"]
        pt = Point({"x" : lon, "y" : lat, "spatialReference" : {"wkid" : 4326}})
        feature = Feature(pt,attr)
        featuresToAdd.append(feature)
    #add all the points  
    #test

    netAtmoFl.edit_features(adds=featuresToAdd)


    logging.info('Python timer trigger function ran at %s', utc_timestamp)
