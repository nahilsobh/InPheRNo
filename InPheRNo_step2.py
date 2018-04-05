"""
This code is written so that we can run Main_TRN_model5p3.py for a number of genes
in a range of indices. The suggestion is to order genes so that top n genes are the 
ones we want to analyze (e.g. sort based on p_gp). 
This is necessary due to the memory leakage of pymc. In other words, defining pymc
models in a loop causes increase of memory useage to the point of using all resources.
Example:
$python Main_TRN_runner_twostage.py -id /workspace/TRN/Data/PGM_TCGA_GTEX -igpa Pvalue_gene_phenotype_1vsAll_FPKM_AdrenalGland_ACC.csv -igp Pvalue_gene_phenotype_ElasticNet_1vsAll_FPKM_TCGA_all_1_100_AdrenalGland_ACC_top_1500.csv -itg  Pvalue_TF_gene_ElasticNet_1vsAll_FPKM_TCGA_all_1_100_AdrenalGland_ACC_top_1500.csv -od /workspace/TRN/Pickles/Pickles_PGM_TCGA_GTEX/Twostage/ 
make sure the file names include either RPKM_GTEX or FPKM_TCGA

The purpose of this wrapper is 1) to allow simple parallelization: different repeats
can be run on different machines and 2) avoid memory leakage (due to some issues
with pymc module at the time this code was written). 
For parallelization, one can use -sr and -er arguments to determine the number of
repeats (out of ---num_repeat) that needs to be considered in this run of the script.

As input, this scripts takes in 3 files: 
1) the file containing p-values of gene-phenotype associations for ALL the genes
(and not just genes of interest). If "None", it is assumed that the genes of interest
are all the genes.
Arguments -id and -igpa can be used to determine the address of this file.
2) the cleaned-up file containing p-values of gene-phenotype associations, only
for genes of interestm which was generated by "InPheRNo_step1" and as defaul was
placed in directory "Results" with the name "Pvalue_gene_phenotype_interest_tmp.csv".
3) the gene-TF pseudo p-value file generated in "InPheRNo_step1" and as defaul was
placed in directory "Results" with the name "Pvalue_gene_tf_tmp.csv".
If you have changed the name of directory and the name
of these files while running "InPheRNo_step1.py", you can provide the new names
using -ido, -igp, and -itg arguments.  




"""


import os
import argparse
import pandas as pd
from scipy.stats import beta, uniform
import numpy as np
from scipy.stats import rv_continuous
import sys
import warnings



###############################################################################
def parse_args():
    """
    Parse the arguments.
    Parse the command line arguments/options using the argparse module
    and return the parsed arguments (as an argparse.Namespace object,
    as returned by argparse.parse_args()).
    Returns:
        argparse.Namespace: the parsed arguments
    """
    parser = argparse.ArgumentParser()
#    parser.add_argument('-l', '--location', default='cloud9', help='laptop or cloud9')
#    parser.add_argument('-s', '--seed', default=1011, help='seed used for random generator')
    parser.add_argument('-id', '--input_dir', default='./Data', help='address of directory containing gene-pheno association for ALL genes')
    parser.add_argument('-igpa', '--input_gene_pheno_all', default='Pvalue_gene_phenotype_all.csv', help='name of file containing gene-phenotype association p-values for all genes, only used to estimate a_gp. If None, it is assumed to be the same as -igp')
    parser.add_argument('-ido', '--input_dir_step_one', default='./Results', help='address of directory containing outputs of InPheRNo_step1.py')
    parser.add_argument('-igp', '--input_gene_pheno', default='Pvalue_gene_phenotype_interest_tmp.csv', help='name of file containing gene-phenotype association p-values')
    parser.add_argument('-itg', '--input_TF_gene', default='Pvalue_gene_tf_tmp.csv', help='name of file containing TF-gene association pseudo p-values generated by InPheRNo_step1.py')
    parser.add_argument('-od', '--output_dir', default='./tmp', help='address of directory for results of different repeats')
    parser.add_argument('-of', '--output_file', default="None", help='prefix to be added to output files')
    parser.add_argument('-atg0', '--A_TF_gene_h0', default="None", help='alpha in beta distribution of TF-gene under Null hypothesis (TF does not regulate gene). If None, it is learnt from data. Otherwise a number must be given.')
    parser.add_argument('-atg1', '--A_TF_gene_h1', default="None", help='alpha in beta distribution of TF-gene under alternative hypothesis (TF regulates gene). If None, it is learnt from data. Otherwise a number must be given.')
    parser.add_argument('-agp', '--A_gene_pheno', default="None", help='alpha in beta distribution of gene-pheno. If None, it is estimated from data (p-value of gene phenotype for all genes is required). Otherwise a number must be given.')
    parser.add_argument('-pt', '--Prior_T', default="None", help='Prior probability of T=1.')
    parser.add_argument('-ptm', '--Prior_T_method', default='fixed', help='Method to set prior probability of T=1. If fixed is chosen and args.priot_T is None, we use 1/(10*n_TF).')
    parser.add_argument('-rtg', '--R_TF_gene', default="None", help='mixing parameter. If None is selected, it is learnt from the data.')
    parser.add_argument('-mnt', '--max_num_TF', default=15, help='Max number of TFs which was used as a parameter in InPheRNo_step1.py.')
    parser.add_argument('-nr', '--num_repeat', default=2, help='Number of the repeats. Repeats are used to ensure stability of results. At least 100 repeats are recommended.')
    parser.add_argument('-sr', '--start_repeat', default=0, help='Start index of the repeat. Useful if program gets killed in the middle or for parallelization.')
    parser.add_argument('-er', '--end_repeat', default='None', help='End index of the repeat. Useful if program gets killed in the middle or for parallelization.')
    parser.add_argument('-ni', '--num_iteration', default=200, help='number of iterations for the PGM.')
    parser.add_argument('-nb', '--num_burn', default=100, help='number of iterations to burn.')
    parser.add_argument('-nt', '--num_thin', default=1, help='number of iterations to thin by')
#    parser.add_argument('-si', '--start_index', default=0, help='start index of the gene to consider')
#    parser.add_argument('-ei', '--end_index', default='None', help='end index of the gene to consider')
    parser.add_argument('-bs', '--batch_size', default=1000, help='number of target genes to run before saving to disk. Smaller value protects against high usage of memroy but increases the run time.')

    args = parser.parse_args()
    return(args)
    
    


###############################################################################
args = parse_args()

delim_gp = ','
delim_tg = ','
delim_gp_a = ','
if args.input_gene_pheno[-3:] in ['tsv', 'txt']:
    delim_gp = '\t'
if args.input_gene_pheno_all[-3:] in ['tsv', 'txt']:
    delim_gp_a = '\t'
if args.input_TF_gene[-3:] in ['tsv', 'txt']:
    delim_tg = '\t'


if not os.path.exists(args.output_dir):
    os.makedirs(args.output_dir)


address_TF_gene = os.path.join(args.input_dir_step_one, args.input_TF_gene)
pvalue_TF_gene = pd.read_csv(address_TF_gene, sep=delim_gp, index_col=0, header=0).T
n_TF = len(pvalue_TF_gene.index)
n_target_gene = len(pvalue_TF_gene.columns)


batch_size = int(args.batch_size)
n_batch = ((n_target_gene - 1) // batch_size) + 1


# end_index = args.end_index

# if int(args.start_index) > n_target_gene: 
#     sys.exit('Start index exceeds maximum number of genes in the data.')
# if end_index == 'None':
#     end_index = n_target_gene
# elif int(end_index) > n_target_gene:
#     end_index = n_target_gene
    
    
#############################################################################
###Estimate a_gp
class beta_unif_gen(rv_continuous):
   def _pdf(self, x, a0, b0, c0):
     return c0 * beta.pdf(x, a=a0, b=b0) + (1-c0) * uniform.pdf(x)


##########################################################################################

if args.input_gene_pheno_all not in  ['None', 'NONE']:
    address_gene_pheno_all = os.path.join(args.input_dir, args.input_gene_pheno_all)
    pvalue_gene_pheno_all = pd.read_csv(address_gene_pheno_all, sep=delim_gp_a, index_col=0, header=0).T


if args.A_gene_pheno in ['None', 'NONE']:
    np.seterr(divide='ignore', invalid='ignore')
    beta_unif_rv = beta_unif_gen(name='beta_unif', a=0., b=1.)
    a_gp_tmp, _, c, _, _= beta_unif_rv.fit(pvalue_gene_pheno_all, fb0=1, floc=0, fscale=1) #fb0 or fc0 fixes b0 and c0, respectively
    if c > 1:
        a_gp_tmp, _, _, _ = beta.fit(pvalue_gene_pheno_all, fb=1, floc=0, fscale=1)
    A_gene = a_gp_tmp
else:
    A_gene = float(args.A_gene_pheno)


##########################################################################################
if args.end_repeat in ['None', 'NONE']:
    end_repeat =  int(args.num_repeat)
else:
    end_repeat = int(args.end_repeat)



for i_r in range(int(args.start_repeat), end_repeat):
    for i_b in range(n_batch):
        start_ind = i_b * batch_size
        if i_b == (n_batch-1):
            end_ind = n_target_gene
        else:
            end_ind = (i_b + 1) * batch_size

        print('a_gp = ', A_gene)
        
        command2run =  "python TRN_twostage.py -atg0 %s -atg1 %s -agp %s -pt %s -ptm %s \
        -rtg %s -igp %s -itg %s -od %s -of %s -mnt %s -ir %s -ni %s -nb %s -nt %s -si %s -ei %s" \
        %(args.A_TF_gene_h0, args.A_TF_gene_h1, A_gene, args.Prior_T, args.Prior_T_method, \
        args.R_TF_gene, os.path.join(args.input_dir_step_one, args.input_gene_pheno), os.path.join(args.input_dir_step_one, args.input_TF_gene), args.output_dir, \
        args.output_file, args.max_num_TF, i_r, args.num_iteration, args.num_burn, args.num_thin, start_ind, end_ind)

        print(command2run)
    
        os.system(command2run)
