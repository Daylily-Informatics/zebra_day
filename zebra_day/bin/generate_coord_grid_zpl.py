import sys
import zebra_day.print_mgr as zdpm


def generate_coarse_grid(x_dim, y_dim):
    step = 50
    zpl_strings = []
    for x in range(0, x_dim, step):
        for y in range(0, y_dim, step):
            zpl_strings.append(f"^FO{x},{y}^A0N,18,18^FD{x}^FS^FO{x},{y+20}^A0N,18,18^FD{y}^FS")
            #zpl_strings.append(f"^FO{x},{y}^A0N,22,22^FD{x},{y}^FS")
    return "^XA" + "".join(zpl_strings) + "^XZ"

def generate_fine_grid(top_left, bottom_right, step=20, expand=50):
    x_start = max(0, top_left[0] - expand)
    y_start = max(0, top_left[1] - expand)
    x_end = bottom_right[0] + expand
    y_end = bottom_right[1] + expand
    zpl_strings = []
    for x in range(x_start, x_end, step):
        for y in range(y_start, y_end, step):
            zpl_strings.append(f"^FO{x},{y}^A0N,20,20^FD{x},{y}^FS")
    return "^XA" + "".join(zpl_strings) + "^XZ"

def main(ip):

    zpld = zdpm.zpl()

    # Part 1: Coarse Grid
    x_dim = int(input("Enter width of the rectangle in dots: "))
    y_dim = int(input("Enter height of the rectangle in dots: "))
    print("\nZPL for coarse grid:\n")
    zpl_string = generate_coarse_grid(x_dim, y_dim)
    print(zpl_string)
    zpld.print_raw_zpl(zpl_string , ip)

    fh = open('./test_800dX800dCoordinateArray.zpl','w')
    fh.write(zpl_string)
    fh.close()
    
    # Part 2: Fine Grid
    #top_left = tuple(map(int, input("\nEnter top-left corner coordinates (x,y) separated by a comma: ").split(',')))
    #bottom_right = tuple(map(int, input("Enter bottom-right corner coordinates (x,y) separated by a comma: ").split(',')))
    #print("\nZPL for fine grid:\n")
    #zpl_string2 = generate_fine_grid(top_left, bottom_right)
    #zpld.print_raw_zpl(zpl_string2 , ip)
    
if __name__ == "__main__":

    main(sys.argv[1])
