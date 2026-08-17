# Algorithm to fetch answers

(This is now out of date and supplanted by code I've written. - Nathan)

The current fetch_answers is too simple. We want to fetch answers that fit with
the intersecting slots and are ordered based on what's most likely to make the
crossword work. To start with the measure of the best words, will be the ones
with the maximum number of possible intersecting words on their worst
intersecting slot.

fetch_answers(grid, cell, direction):
    Slot = get the slot for the cell and direction
    construct glob Pattern of Slot
    Words_for_main_slot = sqlite3("select text from word where GLOB %s", Pattern)

    create a map[words]int called Map
    Populate the keys wirth Words_for_main_slot, setting the values to 0

    get an array of slots, called Slots, that intersect with Slot

    Counter := 0
    for S in Slots:
       construct glob Pattern for S
       calculate i, the index of S that intersects with slot[counter]

       for W in Words_for_main_slot:
           Intersecting_words = sqlite3("select text from word where GLOB %s and text not in words and text and text[i] = word[counter] ", pattern)
           if len(Intersecting_words) < Map[W]
              Map[W] := len(Intersecting_words)
       counter++
       return an array of the words in Map, sorted in ascending order of the values
