import sys
import getopt
from utils import *
from modeling import *
from plotting import *


def main(argv):
    # Image Parameter (default)
    band = "G"                
    pixel_scale = 2.5  # arcsec/pixel
    image_bounds0 = [3100, 1400, 4100, 2400]
    # image_bounds0 = [1800, 2400, 2800, 3400]
    hdu_path = "./data/coadd_Sloan%s_NGC_5907.fits"%band
    dir_name = './fit-real'
    dir_measure = './Measure'
    
    # Fitting Setup (default)
    n_cpu = 4
    method = '3p'
    draw_real = True
    brightest_only = True
    parallel = False 
    leg2d = False
    
    # Fitting Option (default)
    print_progress = True
    draw = True
    save = True

    # Measure Parameter
    r_scale = 12
    Mag_threshold = [14,11]
    
    # Mask Setup
    r_core = [36, 24]
    r_out = None
    wid_strip, n_strip = 24, 48
    
    # Get Script Options
    try:
        optlists, args = getopt.getopt(argv, "f:b:n:r:c:m:I:BLCP",
                                       ["FILTER=", "IMAGE=", "IMAGE_BOUNDS=", "N_COMP=",
                                        "R_SCALE=", "R_CORE=", "MAG_THRESHOLD=", "N_CPU=",
                                        "BRIGHTEST_ONLY", "CONV", "PARALLEL", "NO_PRINT",
                                        "W_STRIP=", "N_STRIP=", "DIR_NAME=", "DIR_MEASURE="])
        opts = [opt for opt, arg in optlists]        
        
    except getopt.GetoptError:
        print('Wrong Option.')
        sys.exit(2)
    
    for opt, arg in optlists:
        if opt in ("-f", "--FILTER"):
            if arg in ["G", "R", "r", "g"]:
                band = arg.upper()
            else:
                print("Filter Not Available.")
                sys.exit(1)
        elif opt in ("-I", "--IMAGE"):
            hdu_path = arg
        elif opt in ("-b", "--IMAGE_BOUNDS"):    
            image_bounds0 = np.array(re.findall(r'\d+', arg), dtype=int)#.reshape(-1,4)
        elif opt in ("-n", "--N_COMP"):
            n_comp = np.int(arg)
            if n_comp == 1:
                method = 'p'
            else:
                if n_comp == 2:
                    method = '2p'
                if n_comp == 3:
                    method = '3p'
        elif opt in ("-r", "--r_SCALE"):
            R_norm = np.float(arg)
        elif opt in ("-c", "--R_CORE"):    
            r_core = np.array(re.findall(r'\d+', arg), dtype=float)
        elif opt in ("-m", "--MAG_THRESHOLD"):    
            Mag_threshold = np.array(re.findall(r'\d+', arg), dtype=float)
        elif opt in ("--W_STRIP"):
            wid_strip = np.float(arg)
        elif opt in ("--N_STRIP"):
            n_strip = np.float(arg)
        elif opt in ("--N_CPU"):
            n_cpu = np.int(arg)
        elif opt in ("--DIR_NAME"):
            dir_name = arg
        elif opt in ("--DIR_MEASURE"):
            dir_measure = arg 
        
    if '-L' in opts: leg2d = True
    if not (('-B' in opts)|("--BRIGHTEST_ONLY" in opts)): brightest_only = False
    if ('-C' in opts)|("--CONV" in opts): draw_real = False
    if ('-P' in opts)|("--PARALLEL" in opts): parallel = True
    if ("--NO_PRINT" in opts): print_progress = False
    
    dir_name = os.path.join(dir_name, "NGC5907-%s-R%dM%dpix_X%dY%d"\
                            %(band, r_scale, r_core[0], image_bounds0[0], image_bounds0[1]))
    if save:
        check_save_path(dir_name, make_new=False)
    
    # Run Fitting!
    ds = Run_Fitting(hdu_path, image_bounds0, method,
                     band=band, Mag_threshold=Mag_threshold,
                     r_scale=r_scale, r_core=r_core, r_out=r_out,
                     pixel_scale=pixel_scale, n_cpu=n_cpu,
                     wid_strip=wid_strip, n_strip=n_strip,
                     parallel=parallel, draw_real=draw_real,
                     brightest_only=brightest_only, leg2d=leg2d,
                     print_progress=print_progress, draw=draw,
                     save=save, dir_name=dir_name, dir_measure=dir_measure)

    return opts

    
def Run_Fitting(hdu_path, image_bounds0,
                method='2p', band="G",
                Mag_threshold=[14,11], r_scale=12,
                r_core=[36,24], r_out=None,
                pad=100, pixel_scale=2.5, 
                wid_strip=24, n_strip=48, 
                n_cpu=None, parallel=False, 
                brightest_only=True, leg2d=False,
                print_progress=True, draw_real=True,
                draw=True, save=False, dir_name='./',
                dir_measure='./Measure'):
    
    ############################################
    # Setup PSF
    ############################################
    
    patch_Xmin0, patch_Ymin0, patch_Xmax0, patch_Ymax0 = image_bounds0
    image_size = (patch_Xmax0 - patch_Xmin0) - 2 * pad
    
    # PSF Parameters
    frac = 0.3                  # fraction of aureole (from fitting stacked PSF)
    beta = 10                                     # moffat beta, in arcsec
    fwhm = 2.5 * pixel_scale                     # moffat fwhm, in arcsec

    n0 = 3.1                    # estimated true power index
    theta_0 = 5.                # radius at which power law is flattened, in arcsec (arbitrary)

    n_s = np.array([n0, 4])                 # power index
    theta_s = np.array([theta_0, 1200])      # transition radius in arcsec

    if method == 'p':
        # Single-power PSF
        params_pow = {"fwhm":fwhm, "beta":beta, "frac":frac, "n":n0, 'theta_0':theta_0}
        psf = PSF_Model(params=params_pow, aureole_model='power')
    else:
        # Multi-power PSF
        params_mpow = {"fwhm":fwhm, "beta":beta, "frac":frac, "n_s":n_s, 'theta_s':theta_s}
        psf = PSF_Model(params=params_mpow, aureole_model='multi-power')

    # Build grid of image for drawing
    psf.make_grid(image_size, pixel_scale=pixel_scale)

    # Generate core and aureole PSF
    psf_c = psf.generate_core()
    psf_e, psf_size = psf.generate_aureole(contrast=1e6, psf_range=image_size)
    star_psf = (1-frac) * psf_c + frac * psf_e
    
    psf_tri = psf.copy()

    ############################################
    # Read
    ############################################
    
    # Read hdu
    with fits.open(hdu_path) as hdul:
        data = hdul[0].data
        header = hdul[0].header
        wcs_data = wcs.WCS(header)

    # Backgroundlevel and estimated std
    try:
        mu, ZP = np.array([header["BACKVAL"], header["REFZP"]]).astype(float)
        print("BACKVAL: %.2f , ZP: %.2f , PIXSCALE: %.2f\n" %(mu, ZP, pixel_scale))

    except KeyError:
        print("BKG / ZP / PIXSCALE missing in header --->")
        ZP = np.float(input("Input a value of ZP :"))
        mu = np.float(input("Manually set a value of background :"))
        data += mu

    # Crop image
    image_bounds = (patch_Xmin0+pad, patch_Ymin0+pad, patch_Xmax0-pad, patch_Ymax0-pad)
    patch_Xmin, patch_Ymin = image_bounds[0], image_bounds[1]

    patch0, seg_patch0 = crop_image(data, image_bounds0, draw=False)

    # Read measurement for faint stars from catalog
    b_name = band.lower()
    fname_catalog = os.path.join(dir_measure, "NGC5907-%s-catalog_PS_%s_all.txt"%(band, b_name))
    tab_catalog = Table.read(fname_catalog, format="ascii")
    
    tab_faint = tab_catalog[(tab_catalog[b_name+"mag"]>=15) & (tab_catalog[b_name+"mag"]<23)]
    tab_faint = crop_catalog(tab_faint, keys=("X_IMAGE_PS", "Y_IMAGE_PS"),
                             bounds=image_bounds)
    tab_faint["FLUX_AUTO"] = 10**((tab_faint["MAG_AUTO"]-ZP)/(-2.5))

    # Read measurement for bright stars
    fname_res_Rnorm = os.path.join(dir_measure, "NGC5907-%s-norm_%dpix_%s15mag_X%dY%d.txt"\
                                   %(band, r_scale, b_name, patch_Xmin0, patch_Ymin0))
    table_res_Rnorm = Table.read(fname_res_Rnorm, format="ascii")
    
    table_res_Rnorm = crop_catalog(table_res_Rnorm, bounds=image_bounds0)

    ############################################
    # Setup Stars
    ############################################
    # Positions & Flux of faint stars from SE
    ma = tab_faint['FLUX_AUTO'].data.mask
    star_pos1 = np.vstack([tab_faint['X_IMAGE_PS'].data[~ma],
                           tab_faint['Y_IMAGE_PS'].data[~ma]]).T - [patch_Xmin, patch_Ymin]
    Flux1 = np.array(tab_faint['FLUX_AUTO'].data[~ma])

    # Positions & Flux (estimate) of faint stars from measured norm
    star_pos2 = np.vstack([table_res_Rnorm['X_IMAGE'],
                           table_res_Rnorm['Y_IMAGE']]).T - [patch_Xmin, patch_Ymin]

    Flux2 = 10**((table_res_Rnorm["MAG_AUTO_corr"]-ZP)/(-2.5))
    
    # Estimate of brightness I at r_scale (I = Intensity - BKG) (and flux)
    # Background is slightly lowered (1 ADU). Note this is not affecting fitting.
    z_norm = table_res_Rnorm['Imean'].data - (mu-1)
#     Flux2 = psf.I2Flux(z_norm, r=r_scale)

    # Thresholds
#     SB_threshold = np.array([27., 24])
#     Flux_threshold = psf.SB2Flux(SB_threshold, BKG=mu, ZP=ZP, r=r_scale)
#     print("\nSurface Brightness Thresholds: %r mag/arcsec^2 at %d pix"%(SB_threshold, r_scale))
    
    Flux_threshold = 10**((Mag_threshold - ZP) / (-2.5))
    SB_threshold = psf.Flux2SB(Flux_threshold, BKG=mu, ZP=ZP, r=r_scale)
    print('\nMagnitude Thresholds: %r'%Mag_threshold)
    print("(<=> Flux Thresholds: %r)"%np.around(Flux_threshold,2))
    print("(<=> Surface Brightness Thresholds: %r mag/arcsec^2 at %d pix)\n"\
          %np.around(SB_threshold,1), r_scale)

    # Combine 
    star_pos = np.vstack([star_pos1, star_pos2])
    Flux = np.concatenate([Flux1, Flux2])
    stars_all = Stars(star_pos, Flux, Flux_threshold=Flux_threshold)
    stars_all.plot_flux_dist(label='All', color='plum')

    # Bright stars in model
    stars0 = Stars(star_pos2, Flux2, Flux_threshold=Flux_threshold,
                   z_norm=z_norm, r_scale=r_scale, BKG=mu)
    stars0 = stars0.remove_outsider(image_size, d=[36, 12], verbose=True)
    stars0.plot_flux_dist(label='Model', color='orange', ZP=ZP, save=save, dir_name=dir_name)
    
    # Maximum amplitude from estimate
    Amp_m = psf.Flux2Amp(Flux).max()

    ############################################
    # Setup Image
    ############################################

    # Make fixed background of dim stars
    image_base = make_base_image(image_size, stars_all, psf_base=star_psf,
                                 psf_size=64, pad=pad, verbose=True)

    # Cutout
    image0 = patch0.copy()
    image = image0[pad:-pad,pad:-pad]

    ############################################
    # Make Mask
    ############################################
    mask = Mask(image0, stars0, image_size, pad=pad, mu=mu)

    mask_base = "./Measure/Seg_PS_X%dY%d.fits" %(patch_Xmin0, patch_Ymin0)
    mask.make_mask_map_dual(r_core=r_core, r_out=r_out, mask_base=mask_base,
                            sn_thre=2.5, n_dilation=5, draw=True, save=save, dir_name=dir_name)
    
    if stars0.n_verybright > 0:
        # S/N + Strip + Cross mask
        mask.make_mask_strip(wid_strip, n_strip,
                             dist_strip=image_size+pad*2, dist_cross=50,
                             clean=True, draw=draw_real, save=save, dir_name=dir_name)
        stars_b = mask.stars_new
        mask_fit = mask.mask_comb
        
    else:
        # S/N mask only
        stars_b = stars0
        mask_fit = mask.mask_deep
        
    plt.show()

    # Choose if only use brightest stars
    if brightest_only:
        stars_vb = Stars(stars_b.star_pos_verybright,
                         stars_b.Flux_verybright,
                         Flux_threshold=stars_b.Flux_threshold,
                         z_norm=stars_b.z_norm_verybright,
                         BKG=stars_b.BKG, r_scale=r_scale)
        stars = stars_vb # for fit
        print("\nOnly model brightest stars in the field.\n")
    else:
        stars = stars_b # for fit

    z_norm_stars = stars.z_norm.copy()
    stars_tri = stars.copy()

    ############################################
    # Estimates
    ############################################
    X = np.array([psf.xx,psf.yy])
    Y = image[~mask_fit].copy().ravel()
    
    # Sky Poisson Noise
    try:
        n_frame = np.int(header['NFRAMES'])
    except KeyError:
        n_frame = 1
    std_poi = np.nanmedian(np.sqrt(Y/0.37/n_frame))
    print("Sky Poisson Noise: %.3f"%std_poi)
    
    # Estimated mu and sigma used as prior
    Y_clip = sigma_clip(image[~mask.mask_deep], sigma=3)
    mu_patch, std_patch = np.mean(Y_clip), np.std(Y_clip)
    print("Estimate of Background: (%.3f +/- %.3f)"%(mu_patch, std_patch))

    ############################################
    # Priors and Likelihood Models for Fitting
    ############################################

    # Make Priors
    prior_tf = set_prior(n_est=n0, mu_est=mu_patch, std_est=std_patch, leg2d=leg2d,
                         n_min=1, theta_in=60, theta_out=300, method=method)
    
#     def loglike_2p(v):
#         _n_s = np.append(v[:2], 4)
#         _theta_s = np.append([theta_0, 10**v[2]], 1200)
#         _mu, _sigma = v[-2], 10**v[-1]

#         psf.update({'n_s':_n_s, 'theta_s':_theta_s})

#         # I varies with sky background
#         stars_tri.z_norm = z_norm_stars + (stars_tri.BKG - _mu)

#         image_tri = generate_image_by_znorm(psf, stars_tri, psf_range=[320,640],
#                                             brightest_only=brightest_only,
#                                             subtract_external=subtract_external,
#                                             psf_scale=pixel_scale,
#                                             parallel=parallel, draw_real=draw_real)
#         image_tri = image_tri + image_base + _mu
                
#         ypred = image_tri[~mask_fit].ravel()
#         residsq = (ypred - Y)**2 / _sigma**2
#         loglike = -0.5 * np.sum(residsq + math.log(2 * np.pi * _sigma**2))

#         if not np.isfinite(loglike):
#             loglike = -1e100

#         return loglike
   
    if method=='2p':
        labels = [r'$n0$', r'$n1$', r'$\theta_1$', r'$\mu$', r'$\log\,\sigma$']
        if leg2d:
            labels = np.insert(labels, 3, [r'$\log\,A_{01}}$', r'$\log\,A_{10}}$'])
            
    elif method=='3p':
        labels = [r'$n0$', r'$n1$', r'$n2$', r'$\theta_1$', r'$\theta_2$', r'$\mu$', r'$\log\,\sigma$']
        if leg2d:
            labels = np.insert(labels, 5, [r'$\log\,A_{01}}$', r'$\log\,A_{10}}$'])
            
    ndim = len(labels)
    
    loglike = set_likelihood(Y, mask_fit, psf_tri, stars_tri,
                             method=method, psf_range=[360,720],
                             z_norm=z_norm_stars, image_base=image_base,
                             brightest_only=brightest_only, leg2d=leg2d,
                             parallel=parallel, draw_real=draw_real)
    
    ############################################
    # Run & Plot
    ############################################
    ds = DynamicNestedSampler(loglike, prior_tf, ndim, n_cpu=n_cpu)
    ds.run_fitting(nlive_init=50, nlive_batch=15, maxbatch=2, print_progress=print_progress)

    ds.cornerplot(labels=labels, figsize=(18, 16), save=save, dir_name=dir_name)
    ds.plot_fit_PSF1D(psf, n_bootstrap=800, leg2d=leg2d,
                      Amp_max=Amp_m, r_core=r_core, save=save, dir_name=dir_name)

    if save:
        fit_info = {'method':method, 'image_size':image_size,
                    'image_bounds0':image_bounds0, 'leg2d':leg2d,
                    'r_core':r_core, 'r_scale':r_scale}
        
        fname='NGC5907-%s-fit_best_X%dY%d_%s'%(band, patch_Xmin0, patch_Ymin0, method)
        if leg2d: fname+='l'
        if brightest_only: fname += 'b'
            
        ds.save_result(fname+'.res', fit_info, dir_name=dir_name)
        
    psf_fit, params = ds.generate_fit(psf, stars0, image_base, leg2d=leg2d, n_out=4, theta_out=1200)

    cal_reduced_chi2((ds.image_fit[~mask_fit]).ravel(), Y, params)
    ds.draw_comparison_2D(image, mask_fit, vmin=457, vmax=1085, save=save, dir_name=dir_name)
    
    if leg2d:
        im=plt.imshow(ds.bkg_fit, vmin=psf_fit.bkg-1-0.05, vmax=psf_fit.bkg-1+0.05)
        colorbar(im)
        if save:
            plt.savefig(os.path.join(dir_name,'%s-Legendre2D_X%dY%d_%s.png'\
                                     %(band, patch_Xmin0, patch_Ymin0, method)), dpi=80)
        else:
            plt.show()


    return ds
    
if __name__ == "__main__":
    main(sys.argv[1:])