import {Component, Input, OnInit, inject} from "@angular/core";
import {FormsModule, NgForm} from "@angular/forms";
import {NodeResolver} from "@app/shared/resolvers/node.resolver";
import {NgClass} from "@angular/common";
import {TranslateModule} from "@ngx-translate/core";
import {UtilsService} from "@app/shared/services/utils.service";
import {Constants} from "@app/shared/constants/constants";
import {AppConfigService} from "@app/services/root/app-config.service";
import {AppDataService} from "@app/app-data.service";
import {UserProfile} from "@app/models/resolvers/user-resolver-model";
import {HttpService} from "@app/shared/services/http.service";

@Component({
    selector: "src-tab7",
    templateUrl: "./tab7.component.html",
    standalone: true,
    imports: [FormsModule, NgClass, TranslateModule]
})
export class Tab7Component implements OnInit {
  @Input() contentForm: NgForm;
  
  idpOptions = [
    { value: 'disabled', label: 'Disabled' },
    { value: 'idp-root', label: 'IDP' }
  ];
  
  tenantIdpOptions = [
    { value: 'disabled', label: 'Disabled' },
    { value: 'idp-tenant', label: 'IDP' },
    { value: 'idp-root', label: 'IDP (Root)' }
  ];
  userProfiles: UserProfile[] = [];

  private utilsService = inject(UtilsService);
  private httpService = inject(HttpService);
  private appConfigService = inject(AppConfigService);
  private appDataService = inject(AppDataService);
  protected nodeResolver = inject(NodeResolver);
  protected readonly Constants = Constants;
  
  isTenantContext = false;

  constructor() {
    this.isTenantContext = !!this.nodeResolver.dataModel.tid && this.nodeResolver.dataModel.tid !== 1;
    if (!this.nodeResolver.dataModel.idp) {
      this.nodeResolver.dataModel.idp = 'disabled';
    }
  }

  ngOnInit() {
    this.httpService.requestUserProfilesResource().subscribe((profiles: UserProfile[]) => {
      this.userProfiles = profiles.filter(profile => profile.name !== "") || [];
      if (!this.nodeResolver.dataModel.default_user_profile && profiles.length) {
        const receiverProfile = this.userProfiles.find(profile => profile.role === "receiver");
        this.nodeResolver.dataModel.default_user_profile = receiverProfile?.id ? receiverProfile.id : "";
      }
    });
  }

  requiresLocalIssuer() {
    return this.nodeResolver.dataModel.idp === 'idp-tenant' ||
           (!this.isTenantContext && this.nodeResolver.dataModel.idp === 'idp-root');
  }

  updateNode() {
    const isRootTenant = !this.isTenantContext || this.nodeResolver.dataModel.tid === 1;
    
    if (isRootTenant) {
      if (this.nodeResolver.dataModel.idp === 'idp-tenant') {
        this.nodeResolver.dataModel.idp = 'disabled';
      }
    }
    
    if (this.requiresLocalIssuer() && !this.nodeResolver.dataModel.idp_issuer) {
      return;
    }
    
    this.utilsService.update(this.nodeResolver.dataModel).subscribe({
      next: () => {
        if (this.appDataService.public?.node) {
          this.appDataService.updatePublic({
            ...this.appDataService.public,
            node: {
              ...this.appDataService.public.node,
              idp: this.nodeResolver.dataModel.idp,
              idp_issuer: this.nodeResolver.dataModel.idp_issuer,
              default_user_profile: this.nodeResolver.dataModel.default_user_profile
            }
          });
        }
        this.appConfigService.reinit(false);
      }
    });
  }
}
