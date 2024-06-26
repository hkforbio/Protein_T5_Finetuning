# -*- coding: utf-8 -*-
"""Copy of  LoRA_T5_XXL_Protein.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1Ea3TLSHphKXi8mvIh0oh-mN9L1oqnsge

# Development Environment
"""

!pip install accelerate evaluate sacremoses wandb dataset transformers bitsandbytes

!pip install rouge-score tensorboard py7zr loralib

!pip install "peft==0.2.0"

"""# Loading Libraries"""

from transformers import T5Tokenizer
from transformers import AutoModelForSeq2SeqLM
from transformers import DataCollatorForSeq2Seq
from transformers import Seq2SeqTrainingArguments
from transformers import Seq2SeqTrainer, Trainer

import torch
import numpy as np
from torch.utils.data import Dataset

import tensorflow as tf
import pandas as pd
from datasets import load_dataset, Dataset
import pyarrow as pa
import evaluate
import wandb

"""# Importing Data"""

import pandas as pd

from google.colab import drive
drive.mount('/content/drive')

with open('/content/drive/MyDrive/GSC_Research_Data/January Research/ortho_one_to_one_text.txt', 'r') as f:
      test = f.read()

test

# Initialize an empty list to store the data
data = []

# Initialize an empty string to store the current protein name and amino acid sequence
current_protein_name = ''
current_amino_acid_sequence = ''

# Open the text file
with open('/content/drive/MyDrive/GSC_Research_Data/January Research/all_test.txt', 'r') as file:
  lines = file.readlines()

# Iterate over the lines in the file
for line in lines:
  # If the line starts with a '>', it means a new protein pair is starting
  if line.startswith('>'):
      # Append the current protein pair to the list
      if current_protein_name:
          data.append([current_protein_name, current_amino_acid_sequence])
      # Start a new protein pair
      current_protein_name = line.strip()
      current_amino_acid_sequence = ''
  else:
      # Otherwise, it's part of the amino acid sequence
      current_amino_acid_sequence += line.strip()

# Append the last protein pair to the list
if current_protein_name:
   data.append([current_protein_name, current_amino_acid_sequence])

# Convert the list to a pandas dataframe
test_df = pd.DataFrame(data, columns=['Protein Name', 'Amino Acid Sequence'])

test_df.shape

test_df.head()

# Assuming test_df is your DataFrame
even_indices = list(range(0, len(test_df), 2))

# Filter rows with even indices
IS_df = test_df[test_df.index.isin(even_indices)]

# Filter rows with odd indices
BS_df = test_df[~test_df.index.isin(even_indices)]

IS_df.head()

BS_df.head()

# Reset index of input_df
input_df = IS_df.reset_index(drop=True)

# Reset index of target_df
output_df = BS_df.reset_index(drop=True)

input_df.head()

output_df.head()

"""## Exploratory Analysis"""

input_df['seqlen'] = input_df['Amino Acid Sequence'].str.len()

output_df["seqlen"] = output_df['Amino Acid Sequence'].str.len()

input_df.head()

output_df.head()

seqlen_input = input_df['seqlen'].tolist()

seqlen_output = output_df['seqlen'].tolist()

"""## Text Pairing"""

output_df = output_df.sort_values(['seqlen'], ascending=[False])

output_df.head()

input_df = input_df.sort_values(['seqlen'], ascending=[False])

input_df.head()

def create_pair(df_input, df_output, i):
    input_bs_protein = df_input.iloc[i,1]
    output_is_protein = df_output.iloc[i,1]

    # output_is_protein = "[start] " + output_is_protein + " [end]"

    return input_bs_protein, output_is_protein

amino_acid_pairs = []
for i in range(len(input_df.index)):
   amino_acid_pairs.append(create_pair(input_df, output_df, i))

print(len(amino_acid_pairs))

for i in range(5):
  print(amino_acid_pairs[i])

amino_acid_pair_df = pd.DataFrame(amino_acid_pairs, columns=['Idonella sakaiensis AA','Bacillus subtillis AA'])

amino_acid_pair_df['BS_seqlen'] = amino_acid_pair_df['Bacillus subtillis AA'].str.len()
amino_acid_pair_df['IS_seqlen'] = amino_acid_pair_df['Idonella sakaiensis AA'].str.len()

amino_acid_pair_df.head()

amino_acid_pair_df.shape

# Drop row if BS_seqlen and IS_seqlen is less than 512

indexes = amino_acid_pair_df[(amino_acid_pair_df['BS_seqlen'] > 512) | (amino_acid_pair_df['IS_seqlen'] > 512)].index
amino_acid_pair_df.drop(indexes, inplace=True)

amino_acid_pair_df.shape

amino_acid_pair_df = amino_acid_pair_df.sort_values(['BS_seqlen'], ascending=[False])
amino_acid_pair_df.head()

amino_acid_pair_df = amino_acid_pair_df.sort_values(['IS_seqlen'], ascending=[False])
amino_acid_pair_df.head()

model_df = amino_acid_pair_df.copy()

model_df = model_df.drop(['BS_seqlen', 'IS_seqlen'], axis=1)

model_df.head()

model_df.shape

model_df['Bacillus subtillis AA'] = model_df['Bacillus subtillis AA'].apply(lambda x: ' '.join(list(x)))
model_df['Idonella sakaiensis AA'] = model_df['Idonella sakaiensis AA'].apply(lambda x: ' '.join(list(x)))

model_df = model_df.reset_index(drop=True)

model_df

"""# Loading Data"""

dataset = model_df.copy()

train_dataset = dataset.sample(frac=0.8, random_state=17)
val_dataset = dataset.drop(train_dataset.index)
hf_dataset = Dataset(pa.Table.from_pandas(dataset)).train_test_split(test_size=0.2)

"""# Tokenization"""

model_checkpoint = "Rostlab/prot_t5_xxl_uniref50"
tokenizer = T5Tokenizer.from_pretrained(model_checkpoint)

tokenizer("M S L")

def preprocess_function(examples):
    inputs = [phrase for phrase in examples["Idonella sakaiensis AA"]]
    targets = [phrase for phrase in examples["Bacillus subtillis AA"]]

    # tokenize each row of inputs and outputs
    model_inputs=tokenizer(inputs, max_length=513, padding='max_length')
    labels=tokenizer(targets, max_length=513, padding='max_length')

    model_inputs["labels"]=labels["input_ids"]
    return model_inputs

processed_datasets = hf_dataset.map(preprocess_function, batched=True, remove_columns=hf_dataset["train"].column_names)

"""# Finetuning"""

model = AutoModelForSeq2SeqLM.from_pretrained(model_checkpoint, load_in_8bit=True, device_map="auto")

model_checkpoint

from peft import LoraConfig, get_peft_model, prepare_model_for_int8_training, TaskType

# Define LoRA Config
lora_config = LoraConfig(
 r=16,
 lora_alpha=32,
 target_modules=["q", "v"],
 lora_dropout=0.05,
 bias="none",
 task_type=TaskType.SEQ_2_SEQ_LM
)
# prepare int-8 model for training
model = prepare_model_for_int8_training(model)

# add LoRA adaptor
model = get_peft_model(model, lora_config)
model.print_trainable_parameters()

# trainable params: 18874368 || all params: 11154206720 || trainable%: 0.16921300163961817

from transformers import DataCollatorForSeq2Seq

# ignore tokenizer pad token in the loss
label_pad_token_id = -100
# Data collator
data_collator = DataCollatorForSeq2Seq(
    tokenizer,
    model=model,
    label_pad_token_id=label_pad_token_id,
    pad_to_multiple_of=8
)

processed_datasets

from transformers import Seq2SeqTrainer, Seq2SeqTrainingArguments

output_dir="April_12th_Test"

# Define training args
training_args = Seq2SeqTrainingArguments(
    output_dir=output_dir,
	auto_find_batch_size=True,
    learning_rate=1e-3, # higher learning rate
    num_train_epochs=3,
    logging_dir=f"{output_dir}/logs",
    logging_strategy="steps",
    logging_steps=100,
    save_strategy="no",
    report_to="tensorboard",
)

# Create Trainer instance
trainer = Seq2SeqTrainer(
    model=model,
    args=training_args,
    data_collator=data_collator,
    train_dataset=processed_datasets["train"],
)
model.config.use_cache = False  # silence the warnings. Please re-enable for inference!

# train model
trainer.train()

peft_model_id="April_13th_results"
trainer.model.save_pretrained(peft_model_id)
tokenizer.save_pretrained(peft_model_id)

"""# Test"""

def calculate_percentage_identity(seq1, seq2):
    # Convert sequences to uppercase for case-insensitive comparison
    seq1 = seq1.upper()
    seq2 = seq2.upper()

    # Perform global sequence alignment
    alignments = global_align(seq1, seq2)
    aligned_seq1, aligned_seq2 = alignments

    # Calculate the percentage identity
    matches = sum(a == b for a, b in zip(aligned_seq1, aligned_seq2))
    percentage_identity = (matches / len(aligned_seq1)) * 100

    return percentage_identity

def global_align(seq1, seq2):
    # Initialize the scoring matrix
    m = len(seq1) + 1
    n = len(seq2) + 1
    score_matrix = [[0] * n for _ in range(m)]

    # Fill in the scoring matrix
    for i in range(1, m):
        score_matrix[i][0] = -i
    for j in range(1, n):
        score_matrix[0][j] = -j

    for i in range(1, m):
        for j in range(1, n):
            match_score = score_matrix[i - 1][j - 1] + (1 if seq1[i - 1] == seq2[j - 1] else -1)
            delete_score = score_matrix[i - 1][j] - 1
            insert_score = score_matrix[i][j - 1] - 1
            score_matrix[i][j] = max(match_score, delete_score, insert_score)

    # Traceback to find the aligned sequences
    aligned_seq1 = []
    aligned_seq2 = []
    i, j = m - 1, n - 1
    while i > 0 or j > 0:
        if i > 0 and j > 0 and score_matrix[i][j] == score_matrix[i - 1][j - 1] + (1 if seq1[i - 1] == seq2[j - 1] else -1):
            aligned_seq1.append(seq1[i - 1])
            aligned_seq2.append(seq2[j - 1])
            i -= 1
            j -= 1
        elif i > 0 and score_matrix[i][j] == score_matrix[i - 1][j] - 1:
            aligned_seq1.append(seq1[i - 1])
            aligned_seq2.append('-')
            i -= 1
        else:
            aligned_seq1.append('-')
            aligned_seq2.append(seq2[j - 1])
            j -= 1

    aligned_seq1.reverse()
    aligned_seq2.reverse()

    return ''.join(aligned_seq1), ''.join(aligned_seq2)

test_seq = "M T T T N P G H R L G L L G R K V G M M R I F T D D G D A I P V T V L D V S N N R V A Q V K T T E T D G Y D A V Q V V Y G A R K A S R V T K P E A G H F A K A G V E A G R V L K E F R V P A A V A A E Y K A G A Q V P V G V F A V G Q L V D V Q G T S I G K G F T G T I K R H N F G S Q R A S H G N S R S H N V P G S I S M A Q D P G R V F P G K K M S G H L G D V T C T V Q N L D I V R I D E A R Q L L L V R G A V P G A K N G H V V V R P A V K A K A Q K G A N"

input_ids = tokenizer(test_seq, return_tensors="pt").input_ids.cuda()
# with torch.inference_mode():
outputs = model.generate(input_ids=input_ids, max_new_tokens=1000, do_sample=True, top_p=0.9)
print(f"input sentence: {test_seq}\n{'---'* 20}")

print(f"summary:\n{tokenizer.batch_decode(outputs.detach().cpu().numpy(), skip_special_tokens=True)[0]}")

data = {'Seq Alignment (Original)': {}, 'Seq Alignment (Generated)': {}}
result_df = pd.DataFrame(data)

# Create a range of 87 indices
new_indices = range(87)

# Reindex the DataFrame with the new indices
result_df = result_df.reindex(new_indices)

result_df

IS_AA = hf_dataset["test"]["Idonella sakaiensis AA"]
BS_AA = hf_dataset["test"]["Bacillus subtillis AA"]

for i in range(87):
    input_seq = IS_AA[i]
    target_seq = BS_AA[i]

    input_ids_seq = tokenizer(input_seq, return_tensors="pt").input_ids.cuda()
    outputs = model.generate(input_ids=input_ids_seq, max_new_tokens=1000, do_sample=True, top_p=0.9)
    target_seq_gen = tokenizer.batch_decode(outputs.detach().cpu().numpy(), skip_special_tokens=True)[0]

    input_target_align = calculate_percentage_identity(input_seq, target_seq)
    gen_target_align = calculate_percentage_identity(input_seq, target_seq_gen)

    print(f"** Example {i} **")
    print("Input seq: ", input_seq)
    print("Targ  seq: ", target_seq)
    print("Gen   seq: ", target_seq_gen)
    print("Input, Target Align: ", input_target_align)
    print("Generated, Target Align: ", gen_target_align)
    print()

    result_df.iloc[i, 0] = input_target_align
    result_df.iloc[i, 1] = gen_target_align