// Import generic module functions
include { initOptions; saveFiles } from './functions'

params.options = [:]
options        = initOptions(params.options)

def VERSIONFRED2 = '2.0.6'
def VERSIONMHCNUGGETS = '2.3.2'

process GENERATE_PROTEINS_FROM_VCF {
    tag "$meta"
    label 'process_medium'

    publishDir "${params.outdir}",
        mode: params.publish_dir_mode,
        saveAs: { filename -> saveFiles(filename:filename, options:params.options, publish_dir:'.', publish_id:meta.id) }

    conda (params.enable_conda ? "bioconda::fred2=2.0.6 bioconda::mhcflurry=1.4.3 bioconda::mhcnuggets=2.3.2" : null)
    if (workflow.containerEngine == 'singularity' && !params.singularity_pull_docker_container) {
        container "https://depot.galaxyproject.org/singularity/mulled-v2-689ae0756dd82c61400782baaa8a7a1c2289930d:a9e10ca22d4cbcabf6b54f0fb5d766ea16bb171e-0"
    } else {
        container "quay.io/biocontainers/mulled-v2-689ae0756dd82c61400782baaa8a7a1c2289930d:a9e10ca22d4cbcabf6b54f0fb5d766ea16bb171e-0"
    }

    input:
        tuple val(meta), path(fasta), path(vcf)

    output:
        tuple val(meta), path("*_vcf.fasta"), emit: vcf_fasta
        path  "*.version.txt", emit: version

    script:
        def prefix   = options.suffix ? "${fasta.baseName}_${options.suffix}" : "${fasta.baseName}_added_vcf"

    """
        variants2fasta.py -v ${vcf} -f ${fasta} -o ${meta.sample}_${prefix}.fasta $options.args

        echo $VERSIONFRED2 > fred2.version.txt
        echo $VERSIONMHCNUGGETS > mhcnuggets.version.txt
        echo \$(mhcflurry-predict --version 2>&1) | sed 's/^.*mhcflurry //; s/ .*\$//' &> mhcflurry.version.txt
    """
}
