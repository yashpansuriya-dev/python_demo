import csv
import random

names = ["Yash", "Rahul", "Amit", "Priya", "Sneha", "Rohan"]
cities = ["Surat", "Ahmedabad", "Mumbai", "Delhi", "Pune"]

with open("sample_data.csv", "w", newline="") as file:
    writer = csv.writer(file)

    # header
    writer.writerow(["id", "name", "age", "city", "salary"])

    # limited rows
    for i in range(10):
        row = [
            i + 1,
            random.choice(names),
            random.randint(18, 40),
            random.choice(cities),
            random.randint(20000, 80000)
        ]
        writer.writerow(row)

print("CSV file generated.")