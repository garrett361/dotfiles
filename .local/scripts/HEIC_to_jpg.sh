#!/bin/bash

for file in *.HEIC;
do heif-convert $file ${file/%.HEIC/.jpg};
done

for file in *.heic;
do heif-convert $file ${file/%.heic/.jpg};
done
