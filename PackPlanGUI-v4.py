#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon May  5 09:34:01 2025

@author: gkurejsepi
"""

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

#%%% Meta updates
Title = "Mouse Packer v4"

# Changelog
Changelog = """
#------#

V4.0 Spare allocator
- Built a new function called assess_animal_list
    - First reads the xlsx, and identifies cohorts
        - for each cohort, it counts genotype and sex

- Built a new function called spare_allocator:
    - uses the user input for number of spares
    - Checks the age spread in that sex per genotype
    - Finds animals as close to the 'median' age
    
- UI Updated:
    - Spares to allocate input fields added
        - dynamically generated after assessing the animal list
    
- Core logic updated:
    - Functions used to automatically execute once spreadsheet was uploaded
    - Split the logic to a new flow:
        - assess_animal_list executes once uploaded
    - spare_allocator (and the remainder) executes once the user clicks generate "pack plan"
        - empty counts as '0' for spares
        
#------#

V3.5 changelog
- Updated to use xlsx instead of CSV
- Removed assign_shippers_v2: Deprecated function that was replaced by assign_shippers_v3
- Changed searching by age from "find nearest" to "find nearest =<7 days apart for age difference in the shipper, otherwise new shipper"
- assign_shippers_v3 updated:
  - Included packing by cohort, so now it can handle multiple cohorts
  - Added ShipperCohortIndex to assist with this and compartments assignments
- assign_compartments updated:
    - Included cohort in the criteria. It will now assign ShipperCompartments by cohort, and reset when it comes to a new cohort
- UI updated:
    - Collapsed Pack Plan into a box
    - Collpased Age Spread in days into a box
    - Added collapsed box that displays this changelog
"""

#%%%

# ---------- FUNCTIONS ---------- #

def sort_genotype_gender(df):
    df = df.sort_values(by=['Genotype', 'Animal Gender', 'Cage', 'Age in Days'], ascending=[True, True, True, True]).reset_index(drop=True)
    return df

def extract_ear_tag(animal_id):
    return animal_id[-3:-1] if isinstance(animal_id, str) and len(animal_id) >= 3 else ""

def assess_animal_list(df):
    summary = []
    for cohort, cohort_df in df.groupby("Sub Project Code"):
        for genotype in cohort_df['Genotype'].unique():
            for sex in ['M', 'F']:
                count = len(cohort_df[(cohort_df['Genotype'] == genotype) & (cohort_df['Animal Gender'] == sex)])
                summary.append({
                    'Sub Project Code': cohort,
                    'Genotype': genotype,
                    'Animal Gender': sex,
                    'Count': count,
                    'Spares to Allocate': 0
                })
    return pd.DataFrame(summary)

def allocate_spares(df, spare_allocations):
    spare_list = []
    spare_ids = set()

    for _, row in spare_allocations.iterrows():
        cohort = row['Sub Project Code']
        genotype = row['Genotype']
        sex = row['Animal Gender']
        n_spares = row['Spares to Allocate']

        subset = df[(df['Sub Project Code'] == cohort) & (df['Genotype'] == genotype) & (df['Animal Gender'] == sex)]
        if not subset.empty and n_spares > 0:
            sorted_subset = subset.sort_values(by='Age in Days')
            median_age = sorted_subset['Age in Days'].median()
            sorted_subset['Age Distance'] = (sorted_subset['Age in Days'] - median_age).abs()
            selected_spares = sorted_subset.nsmallest(n_spares, 'Age Distance')
            spare_list.append(selected_spares.drop(columns=['Age Distance']))
            spare_ids.update(selected_spares.index.tolist())

    df['Is Spare'] = df.index.isin(spare_ids)
    return df

def assign_shippers_v4(df):
    all_assigned = []
    global_shipper_id = 1

    for cohort, cohort_df in df[df['Is Spare'] == False].groupby("Sub Project Code"):
        cohort_df = cohort_df.copy()
        shippers = []
        grouped = cohort_df.groupby(['Genotype', 'Animal Gender', 'Cage'])
        group_list = sorted(grouped, key=lambda x: len(x[1]), reverse=True)

        for (genotype, gender, cage), group_df in group_list:
            animals = group_df.to_dict('records')
            candidate_shippers = []

            for shipper in shippers:
                if (len(shipper) + len(animals) <= 5 and
                    all(a['Animal Gender'] == gender for a in shipper) and
                    all(a['Genotype'] == genotype for a in shipper) and
                    (gender == 'F' or all(a['Cage'] == cage for a in shipper if a['Animal Gender'] == 'M')) and
                    not any(extract_ear_tag(a['Animal Code']) in [extract_ear_tag(b['Animal Code']) for b in shipper] for a in animals)):

                    if gender == 'F':
                        existing_ages = [a['Age in Days'] for a in shipper]
                        new_ages = [a['Age in Days'] for a in animals]
                        age_range = max(existing_ages + new_ages) - min(existing_ages + new_ages)
                        if age_range <= 7:
                            candidate_shippers.append((age_range, shipper))
                    else:
                        candidate_shippers.append((0, shipper))

            if candidate_shippers:
                candidate_shippers.sort(key=lambda x: x[0])
                best_shipper = candidate_shippers[0][1]
                for a in animals:
                    a['Ear Tag'] = extract_ear_tag(a['Animal Code'])
                    a['ShipperIndex'] = global_shipper_id + shippers.index(best_shipper)
                    a['ShipperCohortIndex'] = shippers.index(best_shipper) + 1
                    best_shipper.append(a)
            else:
                new_shipper = []
                for a in animals:
                    a['Ear Tag'] = extract_ear_tag(a['Animal Code'])
                    a['ShipperIndex'] = global_shipper_id + len(shippers)
                    a['ShipperCohortIndex'] = len(shippers) + 1
                    new_shipper.append(a)
                shippers.append(new_shipper)

        assigned = [animal for shipper in shippers for animal in shipper]
        all_assigned.extend(assigned)
        global_shipper_id += len(shippers)

    return pd.DataFrame(all_assigned)

def sort_by_shipper(df):
    return df.sort_values(by=['Genotype', 'Animal Gender', 'ShipperIndex']).reset_index(drop=True)

def assign_compartments(df):
    df = df.copy()
    final_df = []
    cohorts_sorted = sorted(df['Sub Project Code'].unique(), key=lambda x: len(df[df['Sub Project Code'] == x]))

    for cohort in cohorts_sorted:
        cohort_df = df[df['Sub Project Code'] == cohort].copy()
        cohort_df = cohort_df.sort_values(by=['Genotype', 'Animal Gender', 'ShipperCohortIndex']).reset_index(drop=True)
        shipper_compartment = []
        current_compartment_number = 1
        current_compartment_letter = 'a'
        previous_shipper = cohort_df.loc[0, 'ShipperCohortIndex']
        current_gender = cohort_df.loc[0, 'Animal Gender']

        for idx, row in cohort_df.iterrows():
            if row['ShipperCohortIndex'] != previous_shipper:
                if row['Animal Gender'] == current_gender:
                    current_compartment_letter = 'b' if current_compartment_letter == 'a' else 'a'
                    if current_compartment_letter == 'a':
                        current_compartment_number += 1
                else:
                    current_compartment_number += 1
                    current_compartment_letter = 'a'

                previous_shipper = row['ShipperCohortIndex']
                current_gender = row['Animal Gender']

            shipper_compartment.append(f"{current_compartment_number}{current_compartment_letter}")

        cohort_df['Shipper Compartment'] = shipper_compartment
        final_df.append(cohort_df)

    return pd.concat(final_df, ignore_index=True)

# ---------- STREAMLIT APP ----------
st.title(Title)

DisplayChangeLog = st.expander("Updates")
DisplayChangeLog.write(Changelog)

uploaded_file = st.file_uploader("Upload Animal List (Excel)", type="xlsx")

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    df = sort_genotype_gender(df)
    df['Ear Tag'] = df['Animal Code'].apply(extract_ear_tag)
    df['Is Spare'] = False

    st.subheader("Cohort Overview & Spare Allocation")
    spare_df = assess_animal_list(df)

    # Let user enter spares for each row
    for idx in spare_df.index:
        label = f"Spares to allocate for {spare_df.at[idx, 'Sub Project Code']} - {spare_df.at[idx, 'Genotype']} - {spare_df.at[idx, 'Animal Gender']}"
        spare_df.at[idx, 'Spares to Allocate'] = st.number_input(label, min_value=0, value=0, step=1, key=idx)

    if st.button("Generate Pack Plan"):
        df = allocate_spares(df, spare_df)
        processed_df = assign_shippers_v4(df)
        processed_df = sort_by_shipper(processed_df)
        processed_df = assign_compartments(processed_df)

        # Append spares to final output
        spares_df = df[df['Is Spare'] == True].copy()
        spares_df['ShipperIndex'] = 'SPARE'
        spares_df['ShipperCohortIndex'] = ''
        spares_df['Shipper Compartment'] = ''
        final_df = pd.concat([processed_df, spares_df], ignore_index=True)

        # Visualise Pack Plan
        st.subheader("Pack Plan")
        DisplayPackPlan = st.expander("Pack Plan")
        DisplayPackPlan.write(processed_df)

        # Age Spread Plot
        st.subheader("Age Spread per Shipper")
        age_spread_df = processed_df.groupby('ShipperIndex')['Age in Days'].agg(lambda x: max(x) - min(x)).reset_index()
        age_spread_df = age_spread_df.rename(columns={'Age in Days': 'Age Spread'})
        fig, ax = plt.subplots()
        ax.scatter(age_spread_df['ShipperIndex'], age_spread_df['Age Spread'])
        ax.set_title('Age Spread per Shipper')
        ax.set_xlabel('Shipper Index')
        ax.set_ylabel('Age Difference (Days)')
        ax.grid(True)
        
        DisplayAgeSpread = st.expander("Age Spread in Shippers")
        DisplayAgeSpread.pyplot(fig)

        # Download
        output_csv = final_df.to_csv(index=False)
        st.download_button("Download Pack Plan", data=output_csv, file_name="processed_pack_plan.csv", mime="text/csv")
