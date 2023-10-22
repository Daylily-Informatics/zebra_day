# Define your variables:
name = "John"
location = "New York"

# Read the text file:
with open('template.txt', 'r') as file:
    content = file.read()

# Use the `format()` method to replace the placeholders:
formatted_content = content.format(uid_barcode=name, uid_human_readable=location)

print(formatted_content)
