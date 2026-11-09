number = int(input("Enter a positive integer: "))

if number <= 0:
    print("Please enter a positive integer.")
else:
    total = 0
    temp = number

    while temp > 0:
        total += temp % 10
        temp //= 10

    print(f"Sum of digits of {number} = {total}")

import math
from math import *