"""
Convert a CSV-like string into a list of dictionaries 

"""
# --------------------------------------------------------

import string

# --------------------------------------------------------

def covert_dict(csv_data : string) -> list :
    """
        It converts a csv data string into list of
        dictionary and returns it .

        Args :
            csv_data (string) : csv (Comma Separated Values) Data.
        
        Returns :
            list : return data into list of dictionaries.
    """
    students = []

    # Remove any whitespaces and split data line by line
    datas = csv_data.strip().split("\n") 


    keys = datas[0].split(',') # First line is key
    values = datas[1:] # All other lines are values

    for value in values:
        # value is one student details in list.
        # val is list separated by ','.
        val = value.split(',') 
        val[0] = val[0].strip()
        if value == "":
            continue

        # key:value pair converted into dict
        students.append(dict(zip(keys,val)))
    
    return students

# --------------------------------------------------------

def main() -> None:
    csv_data =  """
                id,name,age,city
                1,Yash,20,Ahmedabad
                2,Rahul,21,Surat
                3,Priya,22,Vadodara
                4,Aman,20,Rajkot
                """

    student_details = covert_dict(csv_data)

    for s in student_details:
        print("\n",s)

# ------------------------------------------------------

if __name__ == "__main__":
    main()

