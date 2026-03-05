"""
Simple program to sort student by specific key 
 and filter a list of student with first letter of specified letter.
"""
# -------------------------------------------------------------------

students = [
    {"name":"yash","cgpa":7.8},
    {"name":"nigam","cgpa":2.3},
    {"name":"givraj","cgpa":4.5},
    {"name":"brijrajsinh","cgpa":9.2},
    {"name":"gopal","cgpa":3.8},
    {"name":"raj","cgpa":8.8},
    {"name":"gohil","cgpa":8.2},
    {"name":"krish","cgpa":4.9},
    {"name":"hardik","cgpa":8}
]

# -------------------------------------------------------------------

def sort_dict(data : list , key :str) -> list:
    """
    Return students sorted by the given key.
    """
    if(key in data[0].keys()):
        return sorted(data , key=lambda x : x[key])
    else:
        return []

def filter_dict_by_first_letter(data : list , letter : str) -> list :
    """
    Return students whose names start with the given letter.
    """
    return list(filter(lambda x : x['name'].startswith(letter) , data))

# -------------------------------------------------------------------


def main() -> None:
    """Main Function ."""

    key = input("\n\nEnter the Key to wanted sorted by : ")
    students_sorted_by_cgpa = sort_dict(students , key)

    print("\n Students Sorted by CGPA : ")
    for student in students_sorted_by_cgpa:
        print(student)

    letter = input("\n\nEnter First letter of Students you want : ")

    filtered_students = filter_dict_by_first_letter(students,letter)

    print(f"\nStudents Whose name Starts with  {letter} Are : ")
    print(filtered_students)

# -------------------------------------------------------------------

if __name__ == "__main__":
    main()