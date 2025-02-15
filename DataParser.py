import sys
import pandas as pd
import numpy as np
import argparse
from Bio import SeqIO
from Bio import Seq

WIN_SIZE = 30
WIN_L = 50
WIN_R = 10


def load_genome(fasta, asense=False):

    chrom = []
    seq = []

    with open(fasta, "r") as handle:
        for record in SeqIO.parse(handle, "fasta"):
            chrom.append(record.id)
            if asense:
                seq.append(str(record.seq.complement()[::-1]))
            else:
                seq.append(str(record.seq))

    genome = pd.DataFrame(data={"seq": seq}, index=chrom)

    return genome


def load_signal(RIBO_cov, RIBO_elo, chr_str, len_genome, asense=False):

    columns = ['chrom', 'start', 'stop', 'count']
    sig_df = pd.read_csv(RIBO_cov, header=None, skiprows=1, index_col=0,
                         names=columns, sep="\t")
    sig_el_df = pd.read_csv(RIBO_elo, header=None, skiprows=1, index_col=0,
                            names=columns, sep="\t")

    sig = np.zeros(len_genome)
    sig_el = np.zeros(len_genome)
    print(chr_str, )
    for start, end, count in zip(sig_df.loc[chr_str, "start"],
                                 sig_df.loc[chr_str, "stop"],
                                 sig_df.loc[chr_str, "count"]):
        sig[start:end] = count

    for start, end, count in zip(sig_el_df.loc[chr_str, "start"],
                                 sig_el_df.loc[chr_str, "stop"],
                                 sig_el_df.loc[chr_str, "count"]):
        sig_el[start:end] = count

    return sig, sig_el


def find_start_stop(chrom, start_codons, stop_codons):
    start_sites = []
    stop_sites = []
    for i in range(len(chrom)-3):
        start_codon = chrom[i:i+3]
        if (start_codon == "ATG") or (start_codon == "GTG") or \
                (start_codon == "TTG"):
            for j in range(i, len(chrom)-2, 3):
                codon = chrom[j:j+3]
                if (codon == "TAA") or (codon == "TGA") or (codon == "TAG"):
                    stop_sites.append(j+1)
                    stop_codons.append(chrom[j:j+3])
                    start_sites.append(i+1)
                    start_codons.append(chrom[i:i+3])
                    break

    return start_sites, stop_sites, stop_codons, start_codons


def execute_function(ribo_cov_sense,  ribo_cov_asense, ribo_elo_sense,
                     ribo_elo_asense, fasta, gtf, dest_path):

    df_gtf = pd.read_csv(gtf, sep="\t", comment="#", header=None)
    df_CDS = df_gtf[df_gtf[2] == "CDS"]
    df_as = parse_data(ribo_cov_asense, ribo_elo_asense, fasta, df_CDS,
                       dest_path, asense=True)
    df_s = parse_data(ribo_cov_sense, ribo_elo_sense, fasta, df_CDS,
                      dest_path, asense=False)
    df_all = pd.concat([df_as, df_s])
    df_all.to_csv("{}/data_list.csv".format(dest_path), index=False)

    print("Done")


def parse_data(RIBO_cov, RIBO_elo, fasta, df_CDS, dest_path, asense):

    seq_dict = {"A": 0, "T": 1, "C": 2, "G": 3}
    filenames_seq, filenames_reads, labels_all = [], [], []
    start_codons, in_exons, reads_sum = [], [], []
    start_sites_all, stop_sites_all, stop_sites = [], [], []
    stop_codons, RPK, coverage, RPK_elo = [], [], [], []
    coverage_elo, strands, gene_locs = [], [], []
    nuc_seq, prot_seq = [], []

    genome = load_genome(fasta, asense=asense)
    chr_strs = genome.index.values

    for chr_str in chr_strs:
        sign = "-" if asense else "+"
        print(sign, end="  ")

        chrom = genome.loc[chr_str].values[0]
        start_sites, stop_sites, stop_codons, \
            start_codons = find_start_stop(chrom, start_codons, stop_codons)
        gff_temp = df_CDS[df_CDS[0] == chr_str]

        if asense:
            start_sites_all.append(len(chrom)+1-np.array(start_sites))
            stop_sites_all.append(len(chrom)+1-np.array(stop_sites))
            gff_temp = gff_temp[gff_temp[6] == "-"]
            gff_temp.loc[:, [4, 3]] = len(chrom)+1 - \
                gff_temp.loc[:, [3, 4]].values
        else:
            start_sites_all.append(np.array(start_sites))
            stop_sites_all.append(np.array(stop_sites))
            gff_temp = gff_temp[gff_temp[6] == "+"]

        temp = pd.Series(start_sites)
        labels = temp.isin(gff_temp[3]).values.astype(np.int)
        print(sum(labels))
        for cod in temp:
            mask = np.logical_and(gff_temp.loc[:, 3] <= cod,
                                  gff_temp.loc[:, 4] >= cod)
            in_exons.append((np.any(mask))*1)

        sig, sig_el = load_signal(RIBO_cov, RIBO_elo, chr_str,
                                  len(genome.loc[chr_str].values[0]),
                                  asense)
        seq_temp = chrom[-int(WIN_L):] + chrom + \
            chrom[:int(WIN_R)]

        if asense:
            sig_t = np.concatenate((sig[-int(WIN_R):], sig,
                                    sig[:int(WIN_L)])).astype(int)[::-1]
            sig_t_el = np.concatenate((sig_el[-int(WIN_R):], sig_el,
                                       sig_el[:int(WIN_L)])).astype(int)[::-1]
        else:
            sig_t = np.concatenate((sig[-int(WIN_L):], sig,
                                    sig[:int(WIN_R)])).astype(int)
            sig_t_el = np.concatenate((sig_el[-int(WIN_L):], sig_el,
                                       sig_el[:int(WIN_R)])).astype(int)

        for i, site in enumerate(zip(start_sites, stop_sites)):
            start, stop = site[0], site[1]
            seq = seq_temp[start+WIN_L-21:start+WIN_SIZE+WIN_L-21]
            counts = sig_t[start-1:stop+WIN_L+20]
            lg = np.abs(start-stop)
            ORF_start, ORF_stop = start+WIN_L-1, stop+WIN_L-1
            coverage.append(np.sum(sig_t[ORF_start:ORF_stop] != 0)/lg)
            coverage_elo.append(np.sum(sig_t_el[ORF_start:ORF_stop] != 0)/lg)
            RPK.append(np.sum(sig_t[ORF_start:ORF_stop])/lg)
            RPK_elo.append(np.sum(sig_t_el[ORF_start:ORF_stop])/lg)
            strands.append(sign)
            nuc_seq.append(seq)
            reads_sum.append(int(np.sum(sig_t[start-1:stop+WIN_L-1])))
            prot_seq.append(Seq.translate(seq_temp[ORF_start:ORF_stop+3]))

            seq_img = np.zeros((WIN_SIZE, 4))
            for j, nt in enumerate(seq):
                if nt is not "N":
                    seq_img[j, seq_dict[nt]] = 1
            if asense:
                f_start = len(chrom)-start+1
                gene_locs.append("{}:{}-{}".format(chr_str, len(chrom)-stop+1,
                                                   f_start))
            else:
                f_start = start
                gene_locs.append("{}:{}-{}".format(chr_str, start, stop))
            f_name = "{}/{}_{}{}{}".format(labels[i], WIN_SIZE,
                                           chr_str[:3], sign, f_start)
            if dest_path[-1] == '/':
                dest_path = dest_path[:-1]
            data_name = dest_path.split('/')[-1]
            file_name_seq = "{}_seq.npy".format(f_name)
            file_name_reads = "{}_reads.npy".format(f_name)
            np.save("{}/{}".format(dest_path, file_name_seq), seq_img)
            np.save("{}/{}".format(dest_path, file_name_reads), counts)
            filenames_seq.append("{}/{}".format(data_name, file_name_seq))
            filenames_reads.append("{}/{}".format(data_name, file_name_reads))
            labels_all.append(labels[i])
    start_sites_all = np.array(start_sites_all).ravel()
    stop_sites_all = np.array(stop_sites_all).ravel()
    df_dict = {"filename": filenames_seq, "filename_counts": filenames_reads,
               "label": labels_all, "in_gene": in_exons, "strand": strands,
               "coverage": coverage, "coverage_elo": coverage_elo,
               "rpk": RPK, "rpk_elo": RPK_elo, "start_site": start_sites_all,
               "start_codon": start_codons, "stop_site": stop_sites_all,
               "stop_codon": stop_codons, "locus": gene_locs,
               "prot_seq": prot_seq, "nuc_seq": nuc_seq}
    df = pd.DataFrame(df_dict)
    df = df[["filename", "filename_counts", "label", "in_gene", "strand",
             "coverage", "coverage_elo", "rpk", "rpk_elo", "start_site",
             "start_codon", "stop_site", "stop_codon", "locus", "prot_seq",
             "nuc_seq"]]

    return df


def main():
    parser = argparse.ArgumentParser(description="parse Ribo-seq for use with"
                                     "DeepRibo (Coverage)")
    parser.add_argument('sense_cov', type=str, help="Path to bedgraph "
                        "containing sense riboseq data (Elongating)")
    parser.add_argument('asense_cov', type=str, help="Path to bedgraph "
                        "containing antisense riboseq data (Elongating)")
    parser.add_argument('sense_elo', type=str, help="Path to bedgraph "
                        "containing sense riboseq data (Elongating)")
    parser.add_argument('asense_elo', type=str, help="Path to bedgraph "
                        "containing antisense riboseq data")
    parser.add_argument('fasta', type=str, help="Path to fasta "
                        "containing genome sequence")
    parser.add_argument('gtf', help="Path to gtf/gff containing annotation")
    parser.add_argument('destination', help="Path to output destination. This "
                        "path must contain two folders named 0 and 1")

    args = parser.parse_args()
    execute_function(args.sense_cov,  args.asense_cov, args.sense_elo,
                     args.asense_elo, args.fasta, args.gtf, args.destination)


if __name__ == "__main__":
    sys.exit(main())
