"""
    BMI Calculator -

    A BMI (Body Mass Index) calculator is a simple tool used to 
    estimate whether a person’s body weight is appropriate for 
    their height. It helps classify weight into categories such 
    as underweight, normal weight, overweight, or obese.

"""

# -------------------------------------------------------------------

def weight_status(bmi: float) -> String :
    """
        It Checks BMI Index and returns user's weight status.

          BMI	          Status
        < 18.5	       Underweight
        18.5 - 24.9	   Healthy Weight
        25.0 - 29.9	   Overweight
        ≥ 30.0	       Obese

        Args :
            bmi (float) : BMI (Body Mass Index)
        
        Returns :
            string : returns user's status

    """
    if bmi < 18.5:
        return "UnderWeight"
    elif bmi >=18.5 and bmi < 24.9:
        return "Healthy Weight"
    elif bmi >=25 and bmi < 29.9:
        return "Overweight"
    elif bmi >= 29.9:
        return "Obese"
    else:
        return "Invalid BMI"


def get_bmi(weight : float , height : float) -> float :
    """
        It calcuates BMI index , based on user's 
        weight (In kg.) and Height (in cm.)

        BMI= weight (in kg) / height ^2 (in meter)

        Args :
            weight (float) : User's weight
            height (float) : User's height
        
        Returns :
            float : return bmi
    """
    height = height/100

    bmi = weight / (height*height)
    return bmi 

def get_bmr(weight: float , height: float) -> float |None:
    """
    The Mifflin-St Jeor equation is a highly accurate, widely 
    used formula to calculate Basal Metabolic Rate (BMR). 
    It calculates calories burned at rest using weight 
    (kg), height (cm), and age (years)
    """

    age = int(input("Enter Your Age : "))
    gender  = input("Enter Your Gender ( M / F) : ")

    print("\
           (B :)Just Want BMR : \n\
           (S :)Sedentary: (little/no exercise)\n\
           (L :)Lightly Active: (light exercise/sports 1–3 days/week)\n\
           (M :)Moderately Active: (moderate exercise/sports 3–5 days/week)\n\
           (V :)Very Active: (hard exercise/sports 6–7 days a week)\n\
           (E :)Extra Active: (very hard exercise/physical job")
    
    activity = input("Your Physical Level Activity : ")

    if gender == 'M':
        bmr = (10*weight)+(6.25*height)-(5*age)+5
    elif gender == 'F':
        bmr = (10*weight)+(6.25*height)-(5*age)-161
    else :
        print("Invalid Choice")
        return None
    
    if activity == 'B':
        print("Your BMR is : ",bmr)
    elif activity == 'S':
        print("Your Maintance Calorie is : ",bmr*1.2)
    elif activity == 'L':
        print("Your Maintance Calorie is : ",bmr*1.375)
    elif activity == 'M':
        print("Your Maintance Calorie is : ",bmr*1.55)
    elif activity == 'V':
        print("Your Maintance Calorie is : ",bmr*1.725)
    elif activity == 'E':
        print("Your Maintance Calorie is : ",bmr*1.9)


# -------------------------------------------------------------------

def main() -> None:

    weight = float(input("Enter Your Weight (Kg.) : "))
    height = float(input("Enter Your Height (Cm.) : "))

    bmi = get_bmi(weight,height)
    print(f"Your BMI (Body Mass Index) is : {bmi:.1f}")

    wt_status = weight_status(bmi)
    print("You are ", wt_status)

    print("\n\n")

    get_bmr(weight,height)

# -------------------------------------------------------------------

if __name__ == "__main__":
    main()