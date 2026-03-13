""""
    A Currency converter app , that use to 
    exchange currency rate with real time value with the use 
    of REST APIs.

    API key Used :-
    url = "https://cdn.jsdelivr.net/npm/@fawazahmed0/
    currency-api@latest/v1/currencies/eur.json"

"""

# -------------------------------------------------------------------

import requests

# -------------------------------------------------------------------

def currency_exchange(from_curr: str , to_curr: str, n: float) -> float:
    """
        It exchange the curreny rate and calculate
        the money in real time rate . 

        Args : 
            from_curr (str) : From Currency in symbol
            to_curr (str) : To Currency in symbol
            n (float) : how much money
        
        Returns :
            float : final output money 
    """
    try:
        url = (f"https://cdn.jsdelivr.net/npm/@fawazahmed0/"
               f"currency-api@latest/v1/currencies/{from_curr}.json")
        response = requests.get(url)
        data = response.json()
        rate = data[from_curr][to_curr]
    except Exception:
        print("Enter Valid Symbol")
        return 0
    else:
        return n*rate
    
# -------------------------------------------------------------------
    
def main() -> None:
    """ Main Function . """
    print(currency_exchange("usd", "inr", 5))

    from_curr = input("Enter the From Currency symbol like,\
                       ['usd', 'inr', 'eur'] : ")
    to_curr = input("Enter the To Currency : ")
    n = float(input(f"How much {from_curr} to convert : "))

    final_money = currency_exchange(from_curr, to_curr, n)

    print(f"\n Answer is : {final_money:.2f} {to_curr}")

# -------------------------------------------------------------------

if __name__ == '__main__':
    main()

