"""Contains classes to compute gene-level features.

This module provides:
- Gene: calculate codon counts, amino acid counts, and imprecise codon counts for a single gene
- GeneSet: calculate codon counts, codon frequency, RSCU (relative synonymous codon usage), amino acid counts, and amino acid frequency for a set of genes in an annotated file
- CodonBiasComparison: compare codon bias measurements between two gene sets using linear regression (slope, R^2) and cosine similarity
"""

import os
import re
from typing import List, Union

import numpy as np
import scipy  # pyright: ignore[reportMissingTypeStubs]

from .read_sequence import read_annotated_genes, reverse_complement

# Set up Codon Table with each codon's encoded amino acid (1 letter abbreviation)
CODON_TABLE = {
    "ATA": "I",
    "ATC": "I",
    "ATT": "I",
    "ATG": "M",
    "ACA": "T",
    "ACC": "T",
    "ACG": "T",
    "ACT": "T",
    "AAC": "N",
    "AAT": "N",
    "AAA": "K",
    "AAG": "K",
    "AGC": "S",
    "AGT": "S",
    "AGA": "R",
    "AGG": "R",
    "CTA": "L",
    "CTC": "L",
    "CTG": "L",
    "CTT": "L",
    "CCA": "P",
    "CCC": "P",
    "CCG": "P",
    "CCT": "P",
    "CAC": "H",
    "CAT": "H",
    "CAA": "Q",
    "CAG": "Q",
    "CGA": "R",
    "CGC": "R",
    "CGG": "R",
    "CGT": "R",
    "GTA": "V",
    "GTC": "V",
    "GTG": "V",
    "GTT": "V",
    "GCA": "A",
    "GCC": "A",
    "GCG": "A",
    "GCT": "A",
    "GAC": "D",
    "GAT": "D",
    "GAA": "E",
    "GAG": "E",
    "GGA": "G",
    "GGC": "G",
    "GGG": "G",
    "GGT": "G",
    "TCA": "S",
    "TCC": "S",
    "TCG": "S",
    "TCT": "S",
    "TTC": "F",
    "TTT": "F",
    "TTA": "L",
    "TTG": "L",
    "TAC": "Y",
    "TAT": "Y",
    "TAA": "_",
    "TAG": "_",
    "TGC": "C",
    "TGT": "C",
    "TGA": "_",
    "TGG": "W",
}

# Separate CODON_TABLE dictionary into lists of codons, amino acids, stop codons, and non-degenerate codons (encoded amino acid is specific to one codon alone)
CODON_LIST = list(CODON_TABLE.keys())
AA_LIST = [aa for aa in CODON_TABLE.values() if aa != "_"]
stop_codons = [codon for codon, aa in CODON_TABLE.items() if aa == "_"]
non_degenerate_codons = [
    codon
    for codon, aa in CODON_TABLE.items()
    if list(CODON_TABLE.values()).count(aa) == 1
]

# Amino acid abbreviations conversions
AA_CONVERSIONS = {
    "Ala": "A",
    "Arg": "R",
    "Asn": "N",
    "Asp": "D",
    "Cys": "C",
    "Gln": "Q",
    "Glu": "E",
    "Gly": "G",
    "His": "H",
    "Ile": "I",
    "Leu": "L",
    "Lys": "K",
    "Met": "M",
    "Phe": "F",
    "Pro": "P",
    "Ser": "S",
    "Thr": "T",
    "Trp": "W",
    "Tyr": "Y",
    "Val": "V",
}


# Define Gene class
class Gene:
    """Class representing a gene.

    Args:
        gene_seq (str): The nucleotide sequence of the gene.
        codon_length (int): Length of 1 codon (default is 3).
        gene_id (str): The gene ID from annotations (default is an empty string).
        gene_product (str): The product of the gene from annotations (default is an empty string).
    """

    def __init__(
        self,
        gene_seq: str,
        codon_length: int = 3,
        gene_id: str = "",
        gene_product: str = "",
    ) -> None:
        """Initialize class variables."""
        if len(gene_seq) % codon_length == 0:
            self.seq = gene_seq
            self.codon_length = codon_length
            self.n_codons = len(gene_seq) / codon_length
            self.gene_id = gene_id
            self.gene_product = gene_product
        elif len(gene_seq) % codon_length != 0:
            raise Exception("Gene length is not a multiple of codon length.")

    def calculate_codon_counts(self) -> None:
        """Calculate counts of each unique codon in a gene.

        Populates the following class attributes:
            self.codon_dict (str: int): Each key of dictionary is a unique codon, and the values represent the number of times the associated codon (key) appears in the provided gene sequence.
            self.number_imprecise_codons (int): Number of codons that are not precise (i.e. are not found in expected CODON_LIST).
        """
        self.number_imprecise_codons: int = 0
        self.codon_dict = dict.fromkeys(CODON_LIST, 0)

        for i in range(0, len(self.seq), self.codon_length):
            codon = self.seq[i : i + self.codon_length]
            if codon in self.codon_dict.keys():
                self.codon_dict[codon] += 1
            else:
                self.number_imprecise_codons += 1

        self.percent_imprecise_codons: float = (
            self.number_imprecise_codons / self.n_codons
        )

    def calculate_aa_counts(self) -> None:
        """Calculate counts of each unique amino acid encoded by a gene.

        Populates the following class attributes:
            self.aa_dict (str: int): Each key of dictionary is an unique amino acid, and values represent the number of times the associated amino acid (key) appears to be encoded by codons in the gene sequence.
        If not previously calculated, method will also populate:
            self.codon_dict (str: int): Each key of dictionary is a unique codon, and the values represent the number of times the associated codon (key) appears in the provided gene sequence.
            self.number_imprecise_codons (int): Number of codons that are not precise (i.e. are not found in expected CODON_LIST).
        """
        self.aa_dict = dict.fromkeys(AA_LIST, 0)

        if not hasattr(self, "codon_dict"):
            self.calculate_codon_counts()

        for codon in self.codon_dict:
            if self.codon_dict[codon] != 0 and codon not in stop_codons:
                aa = CODON_TABLE[codon]
                self.aa_dict[aa] += self.codon_dict[codon]

    def calculate_GCn(self) -> None:
        """Calculate GC content at position 1, 2, and 3 of a gene.

        Populates the following class attributes:
            self.GC1 (float): GC content of the gene at position 1.
            self.GC2 (float): GC content of the gene at position 2.
            self.GC3 (float): GC content of the gene at position 3.
        """
        gc1: int = 0
        gc2: int = 0
        gc3: int = 0

        for i in range(0, len(self.seq), self.codon_length):
            codon = self.seq[i : i + self.codon_length]
            for j in range(self.codon_length):
                if codon[j] == "G" or codon[j] == "C":
                    if j == 0:
                        gc1 += 1
                    elif j == 1:
                        gc2 += 1
                    elif j == 2:
                        gc3 += 1

        self.GC1 = gc1 / self.n_codons
        self.GC2 = gc2 / self.n_codons
        self.GC3 = gc3 / self.n_codons


# Define GeneSet class
class GeneSet:
    """Class representing a gene set, usually the genes predicted from a genome sequence.

    Args:
        gene_file (str): Path of annotated genes file containing gene set of interest. Bakta .ffn output format.
    """

    def __init__(self, gene_file: str) -> None:
        """Initialize class variables and read in an annotated genes file, storing Gene objects and metadata in lists."""
        if not gene_file or not os.path.getsize(gene_file):
            raise Exception(
                "Genes file is not provided or empty. Please provide a valid gene file."
            )
        self.id = gene_file
        self.genes: List[Gene] = []
        self.skipped_genes: List[str] = []
        readout = read_annotated_genes(gene_file)

        for out in range(len(readout[0])):
            try:
                self.genes.append(
                    Gene(
                        gene_seq=str(readout[0][out]),
                        gene_id=str(readout[1][out]),
                        gene_product=str(readout[2][out]),
                    )
                )
            except Exception:
                self.skipped_genes.append(str(readout[1][out]))
        percent_skipped = len(self.skipped_genes) / len(readout[0]) * 100
        print(
            f"{percent_skipped}% ({len(self.skipped_genes)}/{len(readout[0])}) of genes skipped. Expect on average ~2% and ~3% of virus and host genes (respectively) to be skipped on the basis of non-divisibility by codon length."
        )

    def codon_counts(
        self, threshold_imprecise: float = 0.0, threshold_skipped_genes: float = 0.5
    ) -> None:
        """Aggregate the counts for each unique codon and imprecise codons across an entire GeneSet.

        Args:
            threshold_imprecise (float): Percentage of imprecise (non-ATGC) codons tolerated in a single gene (default 0.0 or 0%)
            threshold_skipped_genes (float): Tolerated percentage of valid (codon length divisible) genes in GeneSet that have more than threshold_imprecise codons (default 0.5 or 50%)
        Populates the following class attributes:
            self.codon_dict (str: int): Counts of each unique codon across all genes in the GeneSet.
            self.imprecise_codons (int): Total number of imprecise codons found in the GeneSet.
            self.skipped_imprecise_genes (List(str)): IDs of genes in the GeneSet that have more than threshold_imprecise codons.
        """
        self.codon_dict: dict[str, int] = dict.fromkeys(CODON_LIST, 0)
        self.imprecise_codons: int = 0
        self.skipped_imprecise_genes: List[str] = []

        counter = 0
        for gene in self.genes:
            counter += 1
            print(f"Analyzing gene {counter} of {len(self.genes)}")
            gene.calculate_codon_counts()
            self.imprecise_codons += gene.number_imprecise_codons
            if gene.percent_imprecise_codons <= threshold_imprecise:
                for key, val in gene.codon_dict.items():
                    self.codon_dict[key] += val
            else:
                self.skipped_imprecise_genes.append(gene.gene_id)

        if (
            len(self.skipped_imprecise_genes) / len(self.genes)
            > threshold_skipped_genes
        ):
            raise Exception(
                f"Too many skipped genes. {len(self.skipped_imprecise_genes)} genes have > {threshold_imprecise} imprecise codons."
            )
        elif len(self.skipped_imprecise_genes) > 0:
            print(
                f"Skipped {len(self.skipped_imprecise_genes)} genes with too many imprecise codons"
            )

    def codon_frequency(
        self, threshold_imprecise: float = 0.0, threshold_skipped_genes: float = 0.5
    ) -> None:
        """Calculate the frequency of each unique codon in an entire GeneSet.

        Args:
            threshold_imprecise (float): Percentage of imprecise (non-ATGC) codons tolerated in a single gene (default 0.0 or 0%)
            threshold_skipped_genes (float): Tolerated percentage of valid (codon length divisible) genes in GeneSet that have more than threshold_imprecise codons (default 0.5 or 50%)
        Populates the following class attributes:
            self.codon_frq (str: float): Frequency of each unique codon across all genes in the GeneSet.
        If not populated previously by running codon_counts():
            self.codon_dict (str: int): Counts of each unique codon across all genes in the GeneSet.
            self.imprecise_codons (int): Total number of imprecise codons found in the GeneSet.
            self.skipped_imprecise_genes (List[str]): IDs of genes in the GeneSet that have more than threshold_imprecise codons.
        """
        self.codon_frq: dict[str, float] = {}

        if not hasattr(self, "codon_dict"):
            # If aggregate codon counts have not already been calculated, runs codon_counts()
            self.codon_counts(
                threshold_imprecise=threshold_imprecise,
                threshold_skipped_genes=threshold_skipped_genes,
            )

        if hasattr(self, "codon_dict"):
            total = sum(self.codon_dict.values())
            self.codon_frq = {k: (v / total) for k, v in self.codon_dict.items()}

    def amino_acid_counts(
        self, threshold_imprecise: float = 0.0, threshold_skipped_genes: float = 0.5
    ) -> None:
        """Calculate the counts of each unique amino acid encoded by an entire GeneSet.

        Args:
            threshold_imprecise (float): Percentage of imprecise (non-ATGC) codons tolerated in a single gene (default 0.0 or 0%)
            threshold_skipped_genes (float): Tolerated percentage of valid (codon length divisible) genes in GeneSet that have more than threshold_imprecise codons (default 0.5 or 50%)
        Populates the following class attributes:
            self.aa_dict (str: int): Counts of each unique amino acid across all genes in the GeneSet.
        If not populated previously by running codon_counts():
            self.codon_dict (str: int): Counts of each unique codon across all genes in the GeneSet.
            self.imprecise_codons (int): Total number of imprecise codons found in the GeneSet.
            self.skipped_imprecise_genes (List[str]): IDs of genes in the GeneSet that have more than threshold_imprecise codons.
        """
        self.aa_dict: dict[str, int] = dict.fromkeys(AA_LIST, 0)

        if not hasattr(self, "codon_dict"):
            # If aggregate codon counts have not already been calculated, runs codon_counts()
            self.codon_counts(
                threshold_imprecise=threshold_imprecise,
                threshold_skipped_genes=threshold_skipped_genes,
            )

        if hasattr(self, "codon_dict"):
            for codon in self.codon_dict.keys():
                if codon not in stop_codons:
                    aa = CODON_TABLE[codon]
                    self.aa_dict[aa] += self.codon_dict[codon]

    def amino_acid_frequency(
        self, threshold_imprecise: float = 0.0, threshold_skipped_genes: float = 0.5
    ) -> None:
        """Calculate the frequency of each unique amino acid encoded by an entire GeneSet.

        Args:
            threshold_imprecise (float): Percentage of imprecise (non-ATGC) codons tolerated in a single gene (default 0.0 or 0%)
            threshold_skipped_genes (float): Tolerated percentage of valid (codon length divisible) genes in GeneSet that have more than threshold_imprecise codons (default 0.5 or 50%)
        Populates the following class attributes:
            self.aa_frq (str: float): Frequency of each unique amino acid across all genes in the GeneSet.
        If not populated previously by running amino_acid_counts() and codon_counts():
            self.aa_dict (str: int): Counts of each unique amino acid across all genes in the GeneSet.
            self.codon_dict (str: int): Counts of each unique codon across all genes in the GeneSet.
            self.imprecise_codons (int): Total number of imprecise codons found in the GeneSet.
            self.skipped_imprecise_genes (List[str]): IDs of genes in the GeneSet that have more than threshold_imprecise codons.
        """
        self.aa_frq: dict[str, float] = {}

        if not hasattr(self, "aa_dict"):
            # If aggregate amino acid counts have not already been calculated, runs amino_acid_counts()
            self.amino_acid_counts(
                threshold_imprecise=threshold_imprecise,
                threshold_skipped_genes=threshold_skipped_genes,
            )

        if hasattr(self, "aa_dict"):
            total = sum(self.aa_dict.values())
            self.aa_frq = {k: (v / total) for k, v in self.aa_dict.items()}

    def RSCU(
        self, threshold_imprecise: float = 0.0, threshold_skipped_genes: float = 0.5
    ) -> None:
        """Calculate the relative synonymous codon usage (RSCU) of each codon in entire GeneSet.

        Args:
            threshold_imprecise (float): Percentage of imprecise (non-ATGC) codons tolerated in a single gene (default 0.0 or 0%)
            threshold_skipped_genes (float): Tolerated percentage of valid (codon length divisible) genes in GeneSet that have more than threshold_imprecise codons (default 0.5 or 50%)
        Definitions:
            Synonymous codons: codons that encode the same amino acid
            RSCU_dict: codon count / expected frequency (given assumption of equally used synonymous codons)
        Populates the following class attributes:
            self.RSCU (str: float): RSCU of each codon across all genes in the GeneSet.
        If not populated previously by running codon_counts() or codon_frequency():
            self.codon_dict (str: int): Counts of each unique codon across all genes in the GeneSet.
            self.imprecise_codons (int): Total number of imprecise codons found in the GeneSet.
            self.skipped_imprecise_genes (List[str]): IDs of genes in the GeneSet that have more than threshold_imprecise codons.
        """
        self.RSCU_dict: dict[str, float] = dict.fromkeys(CODON_LIST, 0.0)

        if not hasattr(self, "codon_dict"):
            # If aggregate codon counts have not already been calculated, runs codon_counts()
            self.codon_counts(
                threshold_imprecise=threshold_imprecise,
                threshold_skipped_genes=threshold_skipped_genes,
            )

        if hasattr(self, "codon_dict"):
            for codon, count in self.codon_dict.items():
                if count != 0.0:
                    aa = CODON_TABLE[codon]  # aa encoded by current codon iteration
                    synonymous_codons = [
                        key for key, value in CODON_TABLE.items() if value == aa
                    ]  # list of other codons encoding the same aa
                    synonymous_total_count = sum(
                        [self.codon_dict[syn_codon] for syn_codon in synonymous_codons]
                    )  # total number of synonymous codons present in GeneSet
                    expected_frequency = (
                        synonymous_total_count / len(synonymous_codons)
                    )  # expected frequency of current codon given all assumption all synonymous codons are equally likely to encode the aa
                    self.RSCU_dict[codon] = self.codon_dict[codon] / expected_frequency

    def tRNA_counts(self) -> None:
        """Calculate the copy numbers of individual tRNA genes by their associated amino acids and (anti)codons.

        Populates the following class attributes:
            self.tRNA_dict_aa (str: int): Counts of tRNA genes by amino acid across all genes in the GeneSet.
            self.tRNA_dict_tcc (str: int): Counts of tRNA genes by their 'tcc' (tRNA complementary codons) across all genes in the GeneSet.
            self.total_tRNA (int): Total number of tRNA genes (not unique) in the GeneSet.
        """
        # Initialize tRNA count dictionaries, skipping stop codons
        self.tRNA_dict_aa: dict[str, int] = {aa: 0 for aa in AA_LIST}
        self.tRNA_dict_tcc: dict[str, int] = {
            tcc: 0 for tcc in CODON_LIST if tcc not in stop_codons
        }

        # Define RegEx pattern for BAKTA-output tRNA gene products
        gene_product_pattern = re.compile(r"tRNA-\w{3}\(\w{3}\)")

        # Populate tRNA count dictionaries by looping through all gene products in GeneSet
        has_tRNAs = False
        for gene in self.genes:
            if gene_product_pattern.match(gene.gene_product):
                has_tRNAs = True
                aa_3 = gene.gene_product.split("-")[1].split("(")[0]
                aa_1 = AA_CONVERSIONS[aa_3]
                self.tRNA_dict_aa[aa_1] += 1
                anticodon = gene.gene_product.split("(")[1].split(")")[0]
                tcc = reverse_complement(anticodon)
                self.tRNA_dict_tcc[tcc] += 1

        # Calculate total tRNA count
        self.total_tRNA: int = sum(self.tRNA_dict_tcc.values())

        if not has_tRNAs:
            print("No tRNA genes found in the GeneSet.")

    def tRNA_frequency(self) -> None:
        """Calculate the frequency of individual tRNA genes (by their associated amino acids and (anti)codons) out of all tRNA genes in the GeneSet.

        Populates the following class attributes:
            self.tRNA_frq_aa (str: int): Frequencies of tRNA genes by amino acid out of all tRNA genes in the GeneSet.
            self.tRNA_frq_tcc (str: int): Frequencies of tRNA genes by their 'tcc' (tRNA complementary codons) out of all tRNA genes in the GeneSet.
        """
        # If tRNA gene counts have not already been calculated, runs tRNA_counts()
        if (
            not hasattr(self, "tRNA_dict_aa")
            or not hasattr(self, "tRNA_dict_tcc")
            or not hasattr(self, "total_tRNA")
        ):
            self.tRNA_counts()

        # Initialize tRNA frequency dictionaries
        self.tRNA_frq_aa: dict[str, float] = dict.fromkeys(
            self.tRNA_dict_aa.keys(), 0.0
        )
        self.tRNA_frq_tcc: dict[str, float] = dict.fromkeys(
            self.tRNA_dict_tcc.keys(), 0.0
        )

        # Calculate frequency of tRNA genes out of total tRNA counts for the GeneSet
        if self.total_tRNA > 0:
            self.tRNA_frq_aa = {
                k: (v / self.total_tRNA) for k, v in self.tRNA_dict_aa.items()
            }
            self.tRNA_frq_tcc = {
                k: (v / self.total_tRNA) for k, v in self.tRNA_dict_tcc.items()
            }


class CodonBiasComparison:
    """Class for calculating codon bias similarity between a virus GeneSet and a host GeneSet.

    Args:
        host_dict (str: int or str: float): Dictionary of codons/amino acids and their counts/frequencies/RSCUs in a host GeneSet.
        virus_dict (str: int or str: float): Dictionary of codons/amino acids and their counts/frequencies/RSCUs in a virus GeneSet.
    """

    def __init__(
        self,
        host_dict: Union[dict[str, int], dict[str, float]],
        virus_dict: Union[dict[str, int], dict[str, float]],
    ) -> None:
        """Initialize class variables and read in an annotated genes file, storing Gene objects and metadata in lists."""
        self.host_dict: Union[dict[str, int], dict[str, float]] = host_dict
        self.host_list: Union[List[int], List[float]] = list(self.host_dict.values())
        self.virus_dict: Union[dict[str, int], dict[str, float]] = virus_dict
        self.virus_list: Union[List[int], List[float]] = list(self.virus_dict.values())

    def linear_regress(self) -> None:
        """Compute linear regression between host and virus codon bias.

        Populates the following class attributes:
            self.slope (float): Slope of the linear regression line between values from input host_dict and virus_dict
            self.intercept (float): Intercept of the linear regression line between values from input host_dict and virus_dict
        """
        lin_regress = np.polyfit(
            np.array(self.host_list), np.array(self.virus_list), 1
        )  # degree is 1 for linear regression
        self.slope: float = float(lin_regress[0])
        self.intercept: float = float(lin_regress[1])

    def calculate_R2(self) -> None:
        """Compute R^2 value between host and virus codon bias using linear regression.

        Populates the following class attributes:
            self.R2 (float): extracts and calculates the R^2 value from linear regression calculation on values from input host_dict and virus_dict
        If not populated previously by running linear_regress():
            self.slope (float): Slope of the linear regression line between values from input host_dict and virus_dict
            self.intercept (float): Intercept of the linear regression line between values from input host_dict and virus_dict
        """
        if not hasattr(self, "slope") and not hasattr(self, "intercept"):
            self.linear_regress()

        if hasattr(self, "slope") and hasattr(self, "intercept"):
            x = np.array(self.host_list)
            y = np.array(self.virus_list)
            y_predicted = self.slope * x + self.intercept
            residuals_sum_sq = np.sum((y - y_predicted) ** 2)
            total_sum_sq = np.sum((y - np.mean(y)) ** 2)
            self.R2: float = float(1 - (residuals_sum_sq / total_sum_sq))

    def cosine_similarity(self):
        """Compute cosine similarity metric between host and virus codon bias.

        Populates the following class attributes:
            self.cos_similarity (float): calculates the cosine similarity between values from input host_dict and virus_dict
        """
        self.cos_similarity: float = float(
            1 - scipy.spatial.distance.cosine(self.host_list, self.virus_list)
        )


class tRNAMetrics:
    """Class for calculating metrics involving tRNA availability.

    Args:
        virus_GeneSet (GeneSet): GeneSet object representing the virus.
        host_GeneSet (GeneSet): GeneSet object representing the host.
    """

    def __init__(self, virus_GeneSet: GeneSet, host_GeneSet: GeneSet) -> None:
        """Initialize class variables."""
        self.virus_GeneSet: GeneSet = virus_GeneSet
        self.host_GeneSet: GeneSet = host_GeneSet
        """Calculate tRNA counts, totals, and frequencies for both virus and host GeneSets."""
        if not hasattr(self.virus_GeneSet, "tRNA_frq_aa"):
            self.virus_GeneSet.tRNA_frequency()
        if not hasattr(self.host_GeneSet, "tRNA_frq_aa"):
            self.host_GeneSet.tRNA_frequency()

    def virus_TAAI(self, include_virus_tRNA: bool = True) -> None:
        """Calculate accordance index between virus amino acid frequency and corresponding tRNA availability. Note that all amino acids are included in the correlation.

        Args:
            include_virus_tRNA (bool): Whether to additionally calculate an accordance metric that accounts for tRNA gene counts from virus, in addition to that of host (default is True).

        Populates the following class attributes:
            self.virusTAAI_hosttRNA (float): Spearman rank correlation coefficient between host tRNA gene copy frequencies and corresponding viral amino acid frequencies.
            self.virusTAAI_totaltRNA (float): Attribute created and populated only if include_virus_tRNA argument is set to True. Spearman rank correlation coefficient between total tRNA gene copy frequencies (virus and host) and corresponding viral amino acid frequencies.
        """
        # Generate amino acid frequencies for virus GeneSet if not already existent
        if not hasattr(self.virus_GeneSet, "aa_frq"):
            self.virus_GeneSet.amino_acid_frequency()

        # Perform Spearman Rank correlation between virus amino acid frequency and host tRNA availability
        sorted_keys = sorted(self.virus_GeneSet.aa_frq)
        virus_aa_frq_values = [self.virus_GeneSet.aa_frq[key] for key in sorted_keys]
        host_tRNA_frq_aa_values = [
            self.host_GeneSet.tRNA_frq_aa[key] for key in sorted_keys
        ]
        res = scipy.stats.spearmanr(virus_aa_frq_values, host_tRNA_frq_aa_values)
        self.virusTAAI_hosttRNA: float = res.statistic

        # If specified, perform Spearman Rank correlation between virus amino acid frequency and total tRNA availability
        if include_virus_tRNA is True:
            total_tRNA_dict_aa = {
                key: self.host_GeneSet.tRNA_dict_aa.get(key, 0)
                + self.virus_GeneSet.tRNA_dict_aa.get(key, 0)
                for key in set(self.host_GeneSet.tRNA_dict_aa)
                | set(self.virus_GeneSet.tRNA_dict_aa)
            }
            total_virocell_tRNA = sum(total_tRNA_dict_aa.values())
            total_tRNA_frq_aa = {
                k: (v / total_virocell_tRNA) for k, v in total_tRNA_dict_aa.items()
            }
            total_tRNA_frq_aa_values = [total_tRNA_frq_aa[key] for key in sorted_keys]
            res = scipy.stats.spearmanr(virus_aa_frq_values, total_tRNA_frq_aa_values)
            self.virusTAAI_totaltRNA: float = res.statistic

    def virus_TCAI(
        self, skip_nondeg_codons: bool = False, include_virus_tRNA: bool = True
    ) -> None:
        """Calculate accordance index between virus codon frequency and corresponding tRNA availability.

        Args:
            skip_nondeg_codons (bool): Whether to omit non-degenerate codons (codons whose encoded amino acid is specific to one codon alone) from the accordance calculation (default is False). Note stop codons are inherently skipped because they have no associated tRNA.
            include_virus_tRNA (bool): Whether to additionally calculate an accordance metric that accounts for tRNA gene counts from virus, in addition to that of host (default is True).

        Populates the following class attributes:
            self.virusTCAI_hosttRNA (float): Spearman rank correlation coefficient between host tRNA gene copy frequencies and corresponding viral codon frequencies.
            self.virusTCAI_totaltRNA (float): Attribute created and populated only if include_virus_tRNA argument is set to True. Spearman rank correlation coefficient between total tRNA gene copy frequencies (virus and host) and corresponding viral codon frequencies.
        """
        # Generate codon frequencies for virus GeneSet if not already existent
        if not hasattr(self.virus_GeneSet, "codon_frq"):
            self.virus_GeneSet.codon_frequency()

        # Define tRNA dictionaries, skipping non-degenerate codons and including virus tRNAs as specified
        if skip_nondeg_codons is True:
            # Sort and remove non-degenerate and stop codon keys
            irrelevant_codons = non_degenerate_codons + stop_codons
            sorted_keys = [
                key
                for key in sorted(self.virus_GeneSet.codon_frq)
                if key not in irrelevant_codons
            ]
            # Prepare codon and tRNA lists for spearman rank
            virus_codon_frq_values = [
                self.virus_GeneSet.codon_frq[key] for key in sorted_keys
            ]
            host_tRNA_frq_tcc_values = [
                self.host_GeneSet.tRNA_frq_tcc[key] for key in sorted_keys
            ]
            # Prepare tRNA dictionaries for total tRNA accordance metric if specified
            virus_tRNA_dict_tcc = (
                {
                    k: v
                    for k, v in self.virus_GeneSet.tRNA_dict_tcc.items()
                    if k not in irrelevant_codons
                }
                if include_virus_tRNA
                else None
            )
            host_tRNA_dict_tcc = (
                {
                    k: v
                    for k, v in self.host_GeneSet.tRNA_dict_tcc.items()
                    if k not in irrelevant_codons
                }
                if include_virus_tRNA
                else None
            )
        else:
            # Sort and remove stop codon keys only
            sorted_keys = [
                key
                for key in sorted(self.virus_GeneSet.codon_frq)
                if key not in stop_codons
            ]
            # Prepare codon and tRNA lists for spearman rank
            virus_codon_frq_values = [
                self.virus_GeneSet.codon_frq[key] for key in sorted_keys
            ]
            host_tRNA_frq_tcc_values = [
                self.host_GeneSet.tRNA_frq_tcc[key] for key in sorted_keys
            ]
            # Prepare tRNA dictionaries for total tRNA accordance metric if specified
            virus_tRNA_dict_tcc = (
                {
                    k: v
                    for k, v in self.virus_GeneSet.tRNA_dict_tcc.items()
                    if k not in stop_codons
                }
                if include_virus_tRNA
                else None
            )
            host_tRNA_dict_tcc = (
                {
                    k: v
                    for k, v in self.host_GeneSet.tRNA_dict_tcc.items()
                    if k not in stop_codons
                }
                if include_virus_tRNA
                else None
            )

        # Perform Spearman Rank correlation between virus codon frequency and host tRNA availability
        res = scipy.stats.spearmanr(virus_codon_frq_values, host_tRNA_frq_tcc_values)
        self.virusTCAI_hosttRNA: float = res.statistic

        # If specified, perform Spearman Rank correlation between virus codon frequency and total tRNA availability
        if (
            include_virus_tRNA is True
            and host_tRNA_dict_tcc is not None
            and virus_tRNA_dict_tcc is not None
        ):
            total_tRNA_dict_tcc = {
                key: host_tRNA_dict_tcc.get(key, 0) + virus_tRNA_dict_tcc.get(key, 0)
                for key in set(host_tRNA_dict_tcc) | set(virus_tRNA_dict_tcc)
            }
            total_virocell_tRNA = sum(total_tRNA_dict_tcc.values())
            total_tRNA_frq_tcc_values = [
                total_tRNA_dict_tcc[key] / total_virocell_tRNA for key in sorted_keys
            ]
            res = scipy.stats.spearmanr(
                virus_codon_frq_values, total_tRNA_frq_tcc_values
            )
            self.virusTCAI_totaltRNA: float = res.statistic
