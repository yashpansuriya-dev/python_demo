"""
Challenge :
 
Use map and lambda to apply a 10% discount to a list of product prices.
"""

# -------------------------------------------------------------------

def get_discount(prices : list , discount :float) -> list :
    """
    It returns a list with updated discounted prices ,
    with given discount

    Args :
        prices (list) : list of product prices
        discount (float) : discount
    
    Returns :
        list : return new prices list
    """
    discounted_prices = list(map(lambda x : x - ((x * discount)/100) ,
                                 prices))
    return discounted_prices

# -------------------------------------------------------------------

def main() -> None :
    """ Main Function."""
    prices = [100,1200,500,780,1250,8500,4600,]
    discount = 10
    new_prices = get_discount(prices , discount)
    print(new_prices)
    print("hello")

# -------------------------------------------------------------------

if __name__ == "__main__":
    main()