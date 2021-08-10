#!/usr/bin/env python
"""
Commandline tool for (neo)epitope prediction
usage: neoepitopeprediction.py [-h]
                                [-m {netmhc,smmpmbec,syfpeithi,netmhcpan,netctlpan,smm,tepitopepan,arb,pickpocket,epidemix,netmhcii,netmhciipan,comblibsidney,unitope,hammer,svmhc,bimas}]
                                [-v VCF] [-t {VEP,ANNOVAR,SNPEFF}] [-p PROTEINS]
                                [-minl, -maxl {8,9,10,11,12,13,14,15,16,17}]
                                -a ALLELES
                                [-r REFERENCE] [-fINDEL] [-fFS] [-fSNP]
                                -o OUTPUT
Neoepitope prediction for TargetInsepctor.
optional arguments:
    -h, --help            show this help message and exit
    -m, --method {netmhc,smmpmbec,syfpeithi,netmhcpan,netctlpan,smm,tepitopepan,arb,pickpocket,epidemix,netmhcii,netmhciipan,comblibsidney,unitope,hammer,svmhc,bimas},
                        The name of the prediction method
    -v VCF, --vcf VCF     Path to the vcf input file
    -t, --type {VEP,ANNOVAR, SNPEFF}
                        Type of annotation tool used (Variant Effect
                        Predictor, ANNOVAR exonic gene annotation, SnpEff)
    -p, --proteins PROTEINS
                        Path to the protein ID input file (in HGNC-ID)
    -minl, --peptide_min_length {8,9,10,11,12,13,14,15,16,17}
                        The minimal length of peptides
    -maxl, --peptide_max_length {8,9,10,11,12,13,14,15,16,17}
                        The maximal length of peptides
    -a, --alleles ALLELES
                        Alleles string separated by semicolon
    -r, --reference REFERENCE
                        The reference genome used for varinat annotation and
                        calling.
    -fINDEL, --filterINDEL
                        Filter insertions and deletions (including
                        frameshifts)
    -fFS, --filterFSINDEL
                        Filter frameshift INDELs
    -fSNP, --filterSNP    Filter SNPs
    -bind, --predict_bindings
                        Whether to predict bindings or not
    -o OUTPUT, --output OUTPUT
                        Path to the output file
Neoepitope prediction node Consumes a VCF file containing the identified somatic genomic variants, besides a text
file containing HLA alleles, and generates all possible neo-epitopes based on the annotated variants contained in the
VCF file by extracting the annotated transcript sequences from Ensemble [18] and integrating the variants.
Optionally, it consumes a text file, containing gene IDs of the reference system used for annotation, which are used
as filter during the neoepitope generation. The user can specify whether frameshift mutations, deletions,
and insertions should be considered in addition to single nucleotide variations (default). NeoEpitopePrediction
currently supports ANNOVAR [19] and Variant Effect Predictor [20] annotations for GRCh37 and GRCh38 only.
"""
import sys
import argparse
import logging

from Fred2.Core import Protein, Allele, MutationSyntax, Variant
from Fred2.Core.Variant import VariationType
from Fred2.IO import read_lines, MartsAdapter, read_annovar_exonic
from Fred2.EpitopePrediction import EpitopePredictorFactory
from Fred2.Core import generate_transcripts_from_variants, generate_proteins_from_transcripts, generate_peptides_from_proteins, generate_peptides_from_variants
from Fred2.IO.ADBAdapter import EIdentifierTypes, EAdapterFields
from vcf_reader import read_vcf

# logging setup
console = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console.setFormatter(formatter)
LOG = logging.getLogger("VCF Neoepitope Predictor")
LOG.addHandler(console)
LOG.setLevel(logging.INFO)

MARTDBURL = {"GRCH37": "http://grch37.ensembl.org/biomart/martservice?query=",
                "GRCH38": "http://www.ensembl.org/biomart/martservice?query="}  # is correctly set to GRCh38


def read_variant_effect_predictor(file, gene_filter=None):
    """
    Reads a VCF (v4.1) file generated by variant effect predictor and generates variant objects
    :param str file: Path to vcf file
    :param list gene_filter: List of proteins (in HGNC) of inerrest. Variants are filter according to this list
    :return: list(Variant) - a list of Fred2.Core.Variant objects
    """
    vars = []

    def get_type(ref, alt):
        """
            returns the variant type
        """
        if len(ref) == 1 and len(alt) == 1:
            return VariationType.SNP
        if len(ref) > 0 and len(alt) == 0:
            if len(ref) % 3 == 0:
                return VariationType.DEL
            else:
                return VariationType.FSDEL
        if len(ref) == 0 and len(alt) > 0:
            if len(alt) % 3 == 0:
                return VariationType.INS
            else:
                return VariationType.FSINS
        return VariationType.UNKNOWN

    coding_types = {"3_prime_UTR_variant", "5_prime_UTR_variant", "start_lost", "stop_gained", "frameshift_variant",
                    "start_lost", "inframe_insertion", "inframe_deletion", "missense_variant",
                    "protein_altering_variant", "splice_region_variant", "incomplete_terminal_codon_variant",
                    "stop_retained_variant", "synonymous_variant", "coding_sequence_variant"}

    with open(file, "r") as f:
        for i, l in enumerate(f):

            # skip comments
            if l.startswith("#") or l.strip() == "":
                continue

            chrom, gene_pos, var_id, ref, alt, _, filter_flag, info = l.strip().split("\t")[:8]
            coding = {}
            is_synonymous = False

            for co in info.split(","):
                # skip additional info fields without annotation
                try:
                    # Allele|Consequence|IMPACT|SYMBOL|Gene|Feature_type|Feature|BIOTYPE|EXON|INTRON|HGVSc|HGVSp|cDNA_position|CDS_position|Protein_position|Amino_acids|Codons|Existing_variation|DISTANCE|STRAND|FLAGS|SYMBOL_SOURCE|HGNC_ID|TSL|APPRIS|SIFT|PolyPhen|AF|AFR_AF|AMR_AF|EAS_AF|EUR_AF|SAS_AF|AA_AF|EA_AF|gnomAD_AF|gnomAD_AFR_AF|gnomAD_AMR_AF|gnomAD_ASJ_AF|gnomAD_EAS_AF|gnomAD_FIN_AF|gnomAD_NFE_AF|gnomAD_OTH_AF|gnomAD_SAS_AF|CLIN_SIG|SOMATIC|PHENO|PUBMED|MOTIF_NAME|MOTIF_POS|HIGH_INF_POS|MOTIF_SCORE_CHANGE">
                    _, var_type, _, gene, _, transcript_type, transcript_id, _, _, _, _, _, _, transcript_pos, prot_pos, aa_mutation = co.strip().split(
                        "|")[:16]
                except ValueError:
                    LOG.warning("INFO field in different format in line: {}, skipping...".format(str(i)))
                    continue

                # pass every other feature type except Transcript (RegulatoryFeature, MotifFeature.)
                # pass genes that are uninteresting for us
                if transcript_type != "Transcript" or (gene not in gene_filter and gene_filter):
                    continue

                # pass all intronic and other mutations that do not directly influence the protein sequence
                if any(t in coding_types for t in var_type.split("&")):
                    # generate mutation syntax

                    # positioning in Fred2 is 0-based!!!
                    if transcript_pos != "" and '?' not in transcript_pos:
                        coding[transcript_id] = MutationSyntax(transcript_id, int(transcript_pos.split("-")[0]) - 1, -1 if prot_pos == "" else int(prot_pos.split("-")[0]) - 1, co, "", geneID=gene)
                # is variant synonymous?
                is_synonymous = any(t == "synonymous_variant" for t in var_type.split("&"))

            if coding:
                vars.append(
                    Variant(var_id, get_type(ref, alt), chrom, int(gene_pos), ref.upper(), alt.upper(), coding, False,
                            is_synonymous))
    return vars


def main():
    model = argparse.ArgumentParser(description='Neoepitope prediction for TargetInspector.')

    model.add_argument(
        '-m', '--method',
        type=str,
        choices=EpitopePredictorFactory.available_methods().keys(),
        default="bimas",
        help='The name of the prediction method'
    )

    model.add_argument(
        '-v', '--vcf',
        type=str,
        default=None,
        help='Path to the vcf input file'
    )

    model.add_argument(
        '-t', '--type',
        type=str,
        choices=["VEP", "ANNOVAR", "SNPEFF"],
        default="VEP",
        help='Type of annotation tool used (Variant Effect Predictor, ANNOVAR exonic gene annotation, SnpEff)'
    )

    model.add_argument(
        '-p', '--proteins',
        type=str,
        default=None,
        help='Path to the protein ID input file (in HGNC-ID)'
    )

    model.add_argument(
        '-minl', '--peptide_min_length',
        type=int,
        default=8,
        help='Minimum peptide length for epitope prediction'
    )

    model.add_argument(
        '-maxl', '--peptide_max_length',
        type=int,
        default=12,
        help='Maximum peptide length for epitope prediction'
    )

    model.add_argument(
        '-a', '--alleles',
        type=str,
        required=True,
        help='Path to the allele file (one per line in new nomenclature)'
    )

    model.add_argument(
        '-r', '--reference',
        type=str,
        default='GRCh38',
        help='The reference genome used for variant annotation and calling.'
    )

    model.add_argument(
        '-fINDEL', '--filterINDEL',
        action="store_true",
        help='Filter insertions and deletions (including frameshifts)'
    )

    model.add_argument(
        '-fFS', '--filterFSINDEL',
        action="store_true",
        help='Filter frameshift INDELs'
    )

    model.add_argument(
        '-fSNP', '--filterSNP',
        action="store_true",
        help='Filter SNPs'
    )

    model.add_argument(
        '-etk', '--etk',
        action="store_true",
        help=argparse.SUPPRESS
    )

    model.add_argument(
        '-bind', '--predict_bindings',
        action="store_true",
        help='Predict bindings'
    )

    model.add_argument(
        '-o', '--output',
        type=str,
        required=True,
        help='Path to the output file'
    )

    args = model.parse_args()

    martDB = MartsAdapter(biomart=MARTDBURL[args.reference.upper()])
    transcript_to_genes = {}

    if args.vcf is None and args.proteins is None:
        sys.stderr.write("At least a vcf file or a protein id file has to be provided.\n")
        return -1

    # if vcf file is given: generate variants and filter them if HGNC IDs ar given
    if args.vcf is not None:
        protein_ids = []
        if args.proteins is not None:
            with open(args.proteins, "r") as f:
                for l in f:
                    l = l.strip()
                    if l != "":
                        protein_ids.append(l)
        if args.type == "VEP":
            variants = read_variant_effect_predictor(args.vcf, gene_filter=protein_ids)
        elif args.type == "SNPEFF":
            variants = read_vcf(args.vcf)[0]
        else:
            variants = read_annovar_exonic(args.vcf, gene_filter=protein_ids)

        variants = filter(lambda x: x.type != VariationType.UNKNOWN, variants)

        if args.filterSNP:
            variants = filter(lambda x: x.type != VariationType.SNP, variants)

        if args.filterINDEL:
            variants = filter(lambda x: x.type not in [VariationType.INS,
                                                        VariationType.DEL,
                                                        VariationType.FSDEL,
                                                        VariationType.FSINS], variants)

        if args.filterFSINDEL:
            variants = filter(lambda x: x.type not in [VariationType.FSDEL, VariationType.FSINS], variants)

        if not variants:
            sys.stderr.write("No variants left after filtering. Please refine your filtering criteria.\n")
            return -1

        epitopes = []
        minlength=args.peptide_min_length
        maxlength=args.peptide_max_length
        prots = [p for p in generate_proteins_from_transcripts(generate_transcripts_from_variants(variants, martDB, EIdentifierTypes.ENSEMBL))]
        for peplen in range(minlength, maxlength+1):
            peptide_gen = generate_peptides_from_proteins(prots, peplen)

            peptides_var = [x for x in peptide_gen]

            # remove peptides which are not 'variant relevant'
            peptides = [x for x in peptides_var if any(x.get_variants_by_protein(y) for y in x.proteins.keys())]
            epitopes.extend(peptides)

        for v in variants:
            for trans_id, coding in v.coding.iteritems():
                if coding.geneID is not None:
                    transcript_to_genes[trans_id] = coding.geneID
                else:
                    transcript_to_genes[trans_id] = 'None'

    # else: generate protein sequences from given HGNC IDs and then epitopes
    else:
        proteins = []
        with open(args.proteins, "r") as f:
            for l in f:
                ensembl_ids = martDB.get_ensembl_ids_from_id(l.strip(), type=EIdentifierTypes.HGNC)[0]
                protein_seq = martDB.get_product_sequence(ensembl_ids[EAdapterFields.PROTID])
                if protein_seq is not None:
                    transcript_to_genes[ensembl_ids[EAdapterFields.TRANSID]] = l.strip()
                    proteins.append(
                        Protein(protein_seq, gene_id=l.strip(), transcript_id=ensembl_ids[EAdapterFields.TRANSID]))
        epitopes = []
        for length in range(args.peptide_min_length, args.peptide_max_length):
            epitopes.extend(generate_peptides_from_proteins(proteins, length))

    # read in allele list
    alleles = args.alleles

    # predict bindings for all found neoepitopes
    if args.predict_bindings:
        result = EpitopePredictorFactory(args.method).predict(epitopes, alleles=alleles.split(';'))

        with open(args.output, "w") as f:
            alleles = result.columns
            var_column = " Variants" if args.vcf is not None else ""
            f.write("Sequence\tMethod\t" + "\t".join(a.name for a in alleles) + "\tAntigen ID\t" + var_column + "\n")
            for index, row in result.iterrows():
                p = index[0]
                method = index[1]
                proteins = ",".join(
                    set([transcript_to_genes[prot.transcript_id.split(":FRED2")[0]] for prot in p.get_all_proteins()]))
                vars_str = ""

                if args.vcf is not None:
                    vars_str = "\t" + "|".join(set(prot_id.split(":FRED2")[0] + ":" + ",".join( repr(v) for v in set(p.get_variants_by_protein(prot_id)) )
                    for prot_id in p.proteins.iterkeys()
                        if p.get_variants_by_protein(prot_id)))

                f.write(str(p) + "\t" + method + "\t" + "\t".join(
                    "%.3f" % row[a] for a in alleles) + "\t" + proteins + vars_str + "\n")

        if args.etk:
            with open(args.output.rsplit(".", 1)[0] + "_etk.tsv", "w") as g:
                alleles = result.columns
                g.write("Alleles:\t" + "\t".join(a.name for a in alleles) + "\n")
                for index, row in result.iterrows():
                    p = index[0]
                    proteins = " ".join(
                        set([transcript_to_genes[prot.transcript_id.split(":FRED2")[0]] for prot in p.get_all_proteins()]))
                    g.write(str(p) + "\t" + "\t".join("%.3f" % row[a] for a in alleles) + "\t" + proteins + "\n")
    # don't predict bindings!
    # different output format!
    else:
        with open(args.output, "w") as f:
            var_column = " Variants" if args.vcf is not None else ""
            f.write("Sequence\tAntigen ID\t" + var_column + "\n")

            for epitope in epitopes:
                p = epitope
                proteins = ",".join(
                    set([transcript_to_genes[prot.transcript_id.split(":FRED2")[0]] for prot in p.get_all_proteins()]))
                vars_str = ""

                if args.vcf is not None:
                    vars_str = "\t" + "|".join(set(prot_id.split(":FRED2")[0] + ":" + ",".join( repr(v) for v in set(p.get_variants_by_protein(prot_id)) )
                    for prot_id in p.proteins.iterkeys()
                        if p.get_variants_by_protein(prot_id)))

                f.write(str(p) + "\t" + proteins + vars_str + "\n")

        with open(args.output.replace('.csv','.txt'), "w") as f:
            for epitope in epitopes:
                f.write(str(epitope) + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())

