import sys
import zebra_day.print_mgr as zdpm

class ZPLBoundaryTester:
    def __init__(self):
        # Starting coordinates
        self.x = 235
        self.y = 20  ##235,20
        
        # Step size (how much we move the print position each time)
        # Adjust based on the printer's resolution (DPI) and desired granularity.
        self.step = 100

        # Flags
        self.first_print_x = True
        self.first_print_y = True

        self.first_x = None
        self.first_y = None
        self.first_last_x = None
        self.first_last_y = None
        
    def generate_zpl(self):
        #zpl_string = f"^XA^FO{self.x},{self.y}^ADN,30,20^FDXXX^FS^XZ"
        zpl_string = f"^XA^FO{self.x},{self.y}^BY1^B3N,N,40,N,N^FDX^FS^XZ"
        #zpl_string = f"^XA^FO{self.x},{self.y}^A0N,100,100^FDX^FS^XZ"
        return zpl_string

    def process_feedback(self, feedback):
        if feedback == "n":  # not yet
            if not self.first_print_y:
                print("Testing completed.")
                return None
            self.y += self.step
            self.x += self.step
            self.first_print_x = True
            return self.generate_zpl()

        elif feedback == "b":  # begins
            self.first_print_x = False
            self.x += self.step
            return self.generate_zpl()

        elif feedback == "c":  # continuses
            self.x += self.step
            return self.generate_zpl()

        elif feedback == "o":  # off
            if self.first_print_x:
                self.first_print_y = False
            else:
                self.y += self.step
                self.x = 0
                self.first_print_x = True
            return self.generate_zpl()

        else:
            print("Invalid feedback. Please provide a valid feedback string.")
            return None

def main(ip='localhost'):
    tester = ZPLBoundaryTester()
    zpl_string = tester.generate_zpl()

    zpld = zdpm.zpl()
    
    while zpl_string:
        print(f"Send the following ZPL to the printer:\n{zpl_string}")
        feedback = input("Please provide your feedback: ")
        zpl_string = tester.process_feedback(feedback)
        zpld.print_raw_zpl(zpl_string , ip)

if __name__ == "__main__":
    ip = sys.argv[1]
    main(ip)
