# Unique Identifiers

## Maxims

### Be unique in the namespace... if possible, even outside the namespace.
  * Be extremely cautious when working with test and sandbox environments which produce potentially overlapping UIDs to your production systems. Better yet, do not produce UIDs which overlap with other systems you control. `barcode labels IRL`.
  * Issued by a single UID authority.
  
### Absolutely should not change once issued.

### Each distinct thing deserves its own UID.
  * corrolaries:
    * copies of	things are now distinct	things,	and should have	their own UID (metadata and relationships should be stored indicating relationships to other UIDs).
      *	In other words __at all	costs, avoid re-using UIDs for children	of things. This	may momentarily	be convenient, but I can promise you in	the end, you'll	have more than made up for the immediate convenience with an unecessarily fragile and opaque process/system.

### Encode only the unique ID
#### Vigourously avoid encoding any meta data regarding the thing identied by a UID in the UID. Similarly, avoid encoding process/state information.

* There is one exception, 'enterprise UIDs', with a brief prefix indicating object have not been a problem in my experience ([see stripe thinking on this](stripe.com)). These prefixes even offer a benefit when talking about object classes, as well as speeding up certain database queries.
* A few tests to apply when this temptation presents itself (and it will, more than you'd like):
  * Is the information being added to the UID mutable ever? And if the answer is 'almost never' or 'it should not happen(but not actively blocked by a system)', this is BAD.  What if there was a clerical error post UID assignment and now the UID does not reflect the corrected info? Chage the UID? (bad idea, see above)
  * Is there a better way to accomplish whatever use case having the additional data in the UID is attempting to meet (in effectively every situation I've encountered, the answer is yes). Explore how to better serve this use case with other solutions.
      

### Use only alpha numeric characters, ideally all uppercase alpha, no special characters.
* This means no `-`

### Under no circumstances should you add 0's as a prefix to a number being used as a UID
* If a UID is randomly assigning alphanumeric and leading 0s happen to be assigned, is the only exception I can imagine.  Otherwise, this is a huge driver of errors, and mostly of the silent variety.
  * Consider this:  are `EX001` and `EX1` the same? What about `EX0001`?  The answer is that to software at least, these are each unique UIDs. To people, these more often than not are all `EX1`, and are spoken about this way very frequently. Also -  the leading zeros are often omitted when writing the UID down.
    * The arguments for using padded zeros boil down to `they look good in spreadsheets`. Which is not a very compelling reason to adopt a very error prone and fragile design element.
      * What happens when you outgrow the pre-establised number of characters?
      * many s/w systems will auto trim the leading zeros.
      * some barcode scanners will trim leading zeros.
      * What if leading zeros are adjacent to the character 'O'?

### Reading and writing UIDs should not be done by hand
* label printers and scanners.
