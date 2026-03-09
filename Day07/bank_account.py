"""
Challenge :
Build a BankAccount class with deposit, withdraw and get_balance methods
"""
 
# -------------------------------------------------------------------

class BankAccount:
    """ 
    Bank Account Class which has functionality of 
    withdraw money , deposit money and get balance,
    with proper validations .
    """

    def __init__(self, name, curr_money, account_num):
        self.name = name
        self.curr_money = curr_money
        self.__account_num = account_num

    def deposit(self, amount):
        """Add money to account"""
        if(amount < 0):
            print("Your amount must be positive")
            return
        self.curr_money += amount

    def withdraw(self, amount):
        """ WIthdraw money from account"""
        if amount <= 0:
            print("Amount must be positive")
            return
        if amount > self.curr_money:
            print("Insufficient Balance")
            return
        self.curr_money -= amount
    
    def get_balance(self):
        """ Returns current balance."""
        return self.curr_money
    
    def print_details(self):
        print(f"Account Holder  : {self.name} \n"
              f"Current Balance : {self.curr_money}")
    
# -------------------------------------------------------------------

def main() -> None:
    """ Main Function . """
    print("hello")

    yash_account = BankAccount("Yash Pansuriya", 200, 98564712256)

    yash_account.deposit(300)
    yash_account.withdraw(500)

    print("Your Current Balance is : ", yash_account.curr_money)

# -------------------------------------------------------------------

if __name__ == "__main__":
    main()
     