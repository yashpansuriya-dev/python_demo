"""
    It is Weather App , where user has to enter city name
    and it prints its temprature, feels like temp. , 
    weather status . 

"""
# -------------------------------------------------------------------

import requests
 
# -------------------------------------------------------------------

# API key from OpenWeatherMap
API_KEY = "67d0a1e3a07fc273906b8b80cbe0e7dd"

# -------------------------------------------------------------------

def get_weather(city: str) -> dict:
    """
        It fetches data from url with 'get' request
        and returns it.

        Args :
            city (str) : city name for weather 
        
        Returns :
            dict : response data
    """
    try:
        url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&units=metric"
        response = requests.get(url)
        data = response.json()
        return data
    except Exception as e:
        print("Error Occured : ",e)

# -------------------------------------------------------------------

def main() -> None:
    """ Main Function . """
    city = input("Enter City to get temprature : ")

    try:
        weather_data = get_weather(city)

        # If City not found or any error occurs it returns code 200 . 
        if(weather_data['cod'] != 200):
            print(weather_data['message'])
        else:
            print(f"\n {city} Info :- ")
            print(f"Current Temp : {weather_data['main']['temp']} °C")
            print(f"Feels Like : {weather_data['main']['feels_like']} °C")
            print(f"Today Weather Might be : {weather_data['weather'][0]['description']}")
    except:
        print("Error Occured")

# -------------------------------------------------------------------

if __name__ == '__main__':
    main()
    
        
        
