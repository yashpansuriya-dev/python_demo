#Challenge : Build a number guessing game with a limited number of attempts.
import random

def game_start(attempts : int, a : int , b : int) -> None:
    """ 
         It is number Guessing Game , Where User guess Number within 
        specified range .
         User has limited attempts , if user guessed within given attempts
         he win , otherwise he loose.

         Note : 
                it includes both side in range

         Args :
                attempts (int) : Total attempts for user
                a (int) : starting range for number to guess
                b (int) : Ending range for number to guess
        
         Returns : 
                None : it prints user is win or loose.

    """

    n = random.randint(a,b) #it generates random number for given range

    while(attempts > 0):
        user_n = int(input(f"\nGuess a Number Between {a} and {b} : "))
        if(n == user_n):
            print("You Won")
            break
        else:
            attempts -= 1
            print("You guess was incorrect ! Try Again")
            print(f"No. of attempts left - {attempts}")        
            print(" \u2764\uFE0F " * attempts)
    
    if attempts == 0:
        print("Oops ! You Lose the Game")

if __name__ == "__main__":
    game_start(3,1,10)

