# Extracted Manual

## The text

The text came from putting the PDF into the Claude.ai chat which automatically extracted all the text into one long text file.

Then, I ran the following to split the text into sections based on the date, since it followed a consistent format where each page started with this date.

```bash
awk '/^8\/28\/2020/{filename="section_"++i".txt";}{print > filename}' input.txt
```

## The images

1. Each page was converted into a PNG using a PDF reader and saved in `storage/manual/images/raw`
2. The images were then resized to 512x512, forcing them to be square, and saved in `storage/manual/images/512_512`
