^XA          ; Start of ZPL
^MMT         ; Print mode: Tear-off
^PW406       ; Label width: 2 inches x 203 DPI = 406 dots
^LL203       ; Label length: 1 inch x 203 DPI = 203 dots
^LS0         ; Label shift: no shift

; Top-left 'X'
^FO5,5       ; Position: 5 dots from left, 5 dots from top
^A0N,24,24   ; Font: scalable, height: 24 dots, width: 24 dots
^FDX^FS      ; Data: 'X'

; Top-right 'X'
^FO376,5     ; Position: (2 inches - width of 'X' - 5 dots) from left, 5 dots from top
^A0N,24,24
^FDX^FS

; Bottom-left 'X'
^FO5,174     ; Position: 5 dots from left, (1 inch - height of 'X' - 5 dots) from top
^A0N,24,24
^FDX^FS

; Bottom-right 'X'
^FO376,174
^A0N,24,24
^FDX^FS

^PQ1         ; Print quantity: 1 label
^XZ          ; End of ZPL
