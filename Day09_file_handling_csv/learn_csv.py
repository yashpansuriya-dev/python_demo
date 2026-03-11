"""
    It demonstrates csv module and its functions
    and , reading csv , writing csv , csv to dict ,
    and filtering rows by condition and writing it into new file. 
"""

# -------------------------------------------------------------------

import csv

# -------------------------------------------------------------------

def writing_csv(file_name, fields, rows):
    with open(file_name, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(fields)
        writer.writerows(rows)


# Reading CSV
def reading_csv(file_name) -> list:
    fields = []
    rows = []

    with open(file_name, "r") as f:
        reader = csv.reader(f)
        fields = next(reader)

        for row in reader:
            rows.append(row)

    return [fields,rows]


def csv_to_dict(filename) -> list:
    data = reading_csv(filename)
    fields, rows = data[0],data[1]

    details = []

    for row in rows:
        details.append({fields[0]:row[0] ,
                        fields[1]:row[1] ,
                        fields[2]:row[2] ,})
    return details


def csv_to_dict2(filename):
    with open(filename, 'r') as f:
        data_list = []  

        reader = csv.DictReader(f)
        for row in reader:
            data_list.append(row)
    
    return data_list

# -------------------------------------------------------------------

def main() -> None:
    """ Main Function . """
    print("hello")

    fields = ["name", "age", "hobby"]

    rows =  [["Yash", 20, "movies"],
            ["Aman", 22, "cricket"],
            ["Riya", 14, "painting"],
            ["Karan", 23, "gaming"],
            ["Neha", 17, "reading"],
            ["Rohit", 28, "football"],
            ["Sneha", 20, "music"],
            ["Arjun", 15, "gym"],
            ["Priya", 17, "travel"],
            ["Vikram", 11, "photography"],]
    
    # Printing CSV as Dict
    writing_csv("new_csv.csv" , fields, rows)

    details_dict = csv_to_dict("new_csv.csv")
    print("CSV Into Dictinary : ",details_dict)

    print("\nWith DictReader : ", csv_to_dict2("new_csv.csv"))

    # Printing CSV as Table
    print("\n Printing CSV : ")
    data = reading_csv("new_csv.csv")
    fields = data[0]
    rows = data[1]

    print('Field names are: ' + ', '.join(fields))
    for row in rows:
        print(', '.join(row))
    
    # Filtering 
    filter_rows = [row for row in rows if int(row[1]) > 18]

    # Adding FIlter data into new file
    with open("filtered.csv" , "w", newline="") as f:
        writer = csv.writer(f)

        writer.writerow(fields)
        writer.writerows(filter_rows)

# -------------------------------------------------------------------

if __name__ == "__main__":
    main()